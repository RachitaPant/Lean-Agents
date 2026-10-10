"""Wrap BFCL multi-turn simulated APIs as smolagents tools, and score runs with BFCL's own checker.

How BFCL scoring works (see docs/ARCHITECTURE_NOTES.md): the checker does not inspect our live
objects. It re-executes the model's calls, given as strings like "cd(folder='docs')", on fresh
API instances, then compares instance state and call outputs against the ground truth, turn by
turn. So every call that reaches a simulated API is logged here as such a string, grouped as
turns -> steps -> calls, exactly the shape `multi_turn_checker` expects.

The BFCL code itself is vendored, unmodified, under third_party/bfcl_eval (Apache-2.0).
"""

from __future__ import annotations

import ast
import copy
import importlib
import inspect
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from smolagents import Tool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party"))

from bfcl_eval.constants.executable_backend_config import (  # noqa: E402
    CLASS_FILE_PATH_MAPPING,
    MULTI_TURN_FUNC_DOC_FILE_MAPPING,
    STATELESS_CLASSES,
)
from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_checker import multi_turn_checker  # noqa: E402

DATA_DIR = ROOT / "third_party" / "bfcl_eval" / "data"
BASE_TASKS = DATA_DIR / "BFCL_v4_multi_turn_base.json"
BASE_ANSWERS = DATA_DIR / "possible_answer" / "BFCL_v4_multi_turn_base.json"

# BFCL func-doc types -> smolagents input types
_TYPE_MAP = {"float": "number", "dict": "object", "tuple": "array"}


def load_tasks(ids: list[str] | None = None) -> list[dict]:
    """Load multi_turn_base tasks with their ground truth attached (key 'ground_truth')."""
    answers = {}
    for line in BASE_ANSWERS.read_text(encoding="utf-8").splitlines():
        a = json.loads(line)
        answers[a["id"]] = a["ground_truth"]
    tasks = []
    for line in BASE_TASKS.read_text(encoding="utf-8").splitlines():
        t = json.loads(line)
        if ids is None or t["id"] in ids:
            t["ground_truth"] = answers[t["id"]]
            tasks.append(t)
    if ids is not None:
        missing = set(ids) - {t["id"] for t in tasks}
        if missing:
            raise KeyError(f"unknown task ids: {sorted(missing)}")
        tasks.sort(key=lambda t: ids.index(t["id"]))
    return tasks


def load_func_docs(class_name: str) -> list[dict]:
    path = DATA_DIR / "multi_turn_func_doc" / MULTI_TURN_FUNC_DOC_FILE_MAPPING[class_name]
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _convert_schema(schema: dict) -> dict:
    """Map a BFCL parameter schema to JSON-schema types smolagents accepts (recursively)."""
    out = {}
    for key, value in schema.items():
        if key == "type":
            out[key] = _TYPE_MAP.get(value, value)
        elif key == "items" and isinstance(value, dict):
            out[key] = _convert_schema(value)
        elif key == "properties" and isinstance(value, dict):
            out[key] = {k: _convert_schema(v) for k, v in value.items()}
        else:
            out[key] = value
    return out


def format_call(name: str, args: dict) -> str:
    """Render a call the way BFCL ground truth does: name(k=repr(v), ...)."""
    return f"{name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"


def parse_call(call: str, param_order: list[str]) -> tuple[str, dict]:
    """Parse a BFCL call string ("sort('a.pdf')", "cd(folder='x')") into (name, kwargs)."""
    node = ast.parse(call, mode="eval").body
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        raise ValueError(f"not a simple call: {call}")
    kwargs = {param_order[i]: ast.literal_eval(a) for i, a in enumerate(node.args)}
    kwargs.update({kw.arg: ast.literal_eval(kw.value) for kw in node.keywords})
    return node.func.id, kwargs


class BFCLTool(Tool):
    """One BFCL API method exposed as a smolagents tool. Logs each executed call to the env."""

    output_type = "string"
    skip_forward_signature_validation = True

    def __init__(self, doc: dict, method, env: "BFCLEnv"):
        params = doc["parameters"]
        required = set(params.get("required", []))
        self.name = doc["name"]
        self.description = doc["description"]
        self.inputs = {}
        for pname, pschema in params.get("properties", {}).items():
            spec = _convert_schema(pschema)
            spec.pop("default", None)  # defaults are applied by the method itself
            if pname not in required:
                # smolagents' "nullable" flag is not standard JSON schema; Groq ignores it and
                # rejects `null` for optional args server-side. A ["T", "null"] type is standard.
                spec["nullable"] = True
                spec["type"] = [spec["type"], "null"]
            self.inputs[pname] = spec
        self.param_order = list(params.get("properties", {}))
        self.response_doc = doc.get("response", {})  # BFCL documents outputs too; used by C1 retrieval
        self._method = method
        self._env = env
        super().__init__()

    def forward(self, **kwargs) -> str:
        # Optional args the model set to null mean "use the default": drop them.
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        self._env.record(format_call(self.name, kwargs))
        try:
            result = self._method(**kwargs)
        except Exception as e:  # mirror BFCL's executor: errors become the observation
            return f"Error during execution: {e}"
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result)
        except TypeError:
            return str(result)


class BFCLEnv:
    """Live simulated-API instances for one BFCL task, plus the per-turn call log."""

    def __init__(self, task: dict):
        self.task = task
        self.instances: dict[str, Any] = {}
        for class_name in task["involved_classes"]:
            module = importlib.import_module(CLASS_FILE_PATH_MAPPING[class_name])
            instance = getattr(module, class_name)()
            if class_name not in STATELESS_CLASSES:
                config = copy.deepcopy(task["initial_config"].get(class_name, {}))
                instance._load_scenario(config, long_context=False)
            self.instances[class_name] = instance

        self.tools: dict[str, BFCLTool] = {}
        for class_name, instance in self.instances.items():
            methods = dict(inspect.getmembers(instance, predicate=inspect.ismethod))
            for doc in load_func_docs(class_name):
                self.tools[doc["name"]] = BFCLTool(doc, methods[doc["name"]], self)

        # calls[turn][step] = ["cd(folder='x')", ...]
        self.calls: list[list[list[str]]] = []
        self._pending: list[str] = []

    # --- call log -------------------------------------------------------------------------
    def start_turn(self) -> None:
        self.end_step()
        self.calls.append([])

    def record(self, call: str) -> None:
        self._pending.append(call)

    def end_step(self, *_args, **_kwargs) -> None:
        """Close the current step. Also usable as a smolagents step callback."""
        if self._pending:
            self.calls[-1].append(self._pending)
            self._pending = []

    # --- helpers --------------------------------------------------------------------------
    def call_ground_truth(self, call: str) -> str:
        """Execute one ground-truth call string through our tools (used by tests)."""
        name = call.split("(", 1)[0]
        tool = self.tools[name]
        _, kwargs = parse_call(call, tool.param_order)
        return tool.forward(**kwargs)


def score(task: dict, calls: list[list[list[str]]]) -> dict:
    """Score a run with BFCL's official multi-turn checker. Returns {'valid': bool, ...}."""
    if len(calls) != len(task["ground_truth"]):
        raise ValueError(f"{task['id']}: {len(calls)} turns logged, {len(task['ground_truth'])} expected")
    # The checker caches instances in module globals keyed by model_name + task id, so a
    # fresh name per call keeps repeated scoring of the same task independent.
    return multi_turn_checker(
        multi_turn_model_result_list_decoded=calls,
        multi_turn_ground_truth_list=task["ground_truth"],
        test_entry=task,
        test_category="multi_turn_base",
        model_name=f"lean_{uuid.uuid4().hex[:8]}",
    )
