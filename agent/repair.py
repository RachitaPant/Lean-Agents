"""C2: validate-and-repair helpers. Pure functions; the agent wiring is in agent/lean_agent.py.

Built from the failures recorded in Phases 1-4 (docs/PHASE_LOG.md):
- invented tool names (`answer`, `json`) that the provider rejects with HTTP 400;
- unknown argument names (`cityA` repeated 7x) after a message that never said which tool or
  which arguments were valid;
- invented wrappers on zero-argument tools (`{"arguments": {}}`, `{"args": {}}`);
- unparseable output (HTTP 400 `output_parse_failed`).
Every message names the tool and spells out its real signature, so the model can fix the call.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from smolagents import Tool

WRAPPER_KEYS = ("arguments", "args", "kwargs", "parameters", "params", "input")
_ENUM = re.compile(r"\[Enum\]:\s*(\[.*?\])", re.S)
_JSON_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}

# Categories of the failure taxonomy (PROJECT_PLAN Phase 5)
WRONG_TOOL = "wrong_tool"  # a tool name that doesn't exist
WRONG_ARGUMENT = "wrong_argument"  # unknown/missing argument, wrong type, value outside an enum
MALFORMED = "malformed_output"  # output the provider could not parse as a call or a reply
WRAPPER = "wrapper_unwrapped"  # invented {"arguments": {...}} wrapper, fixed silently


@dataclass(frozen=True)
class RepairOptions:
    validate_args: bool = True  # targeted client-side validation (+ unwrap wrappers)
    recover_provider_errors: bool = True  # turn provider HTTP 400s into feedback, not crashes
    side_effect_notes: bool = True  # tell the model which state-changing calls already succeeded
    max_repairs_per_turn: int = 3  # after this, the error is fatal again (no infinite loops)

    def to_dict(self) -> dict:
        return asdict(self)


# --- signatures and validation --------------------------------------------------------------

def enum_values(spec: dict) -> list | None:
    """BFCL puts allowed values in the description: '... [Enum]: ["START", "STOP"]'."""
    if "enum" in spec:
        return list(spec["enum"])
    m = _ENUM.search(str(spec.get("description", "")))
    if not m:
        return None
    try:
        values = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return values if isinstance(values, list) else None


def _type_names(spec: dict) -> list[str]:
    t = spec.get("type", "any")
    return [x for x in (t if isinstance(t, list) else [t]) if x != "null"]


def is_optional(spec: dict) -> bool:
    return bool(spec.get("nullable")) or "null" in (spec.get("type") if isinstance(spec.get("type"), list) else [])


def tool_signature(tool: Tool) -> str:
    """`estimate_distance(cityA: string, cityB: string)`, optional args marked with `?`."""
    parts = []
    for name, spec in tool.inputs.items():
        types = "|".join(_type_names(spec)) or "any"
        allowed = enum_values(spec)
        if allowed:
            types += f" one of {json.dumps(allowed)}"
        parts.append(f"{name}{'?' if is_optional(spec) else ''}: {types}")
    return f"{tool.name}({', '.join(parts)})"


def unwrap_arguments(tool: Tool, args) -> tuple[dict, bool]:
    """{"arguments": {...}} → {...} when the tool has no such parameter. Returns (args, changed)."""
    if not isinstance(args, dict) or len(args) != 1:
        return args, False
    (key, value), = args.items()
    if key in WRAPPER_KEYS and key not in tool.inputs and isinstance(value, dict):
        return value, True
    return args, False


def _type_ok(value, spec: dict) -> bool:
    if value is None:
        return is_optional(spec)
    names = _type_names(spec)
    if not names or "any" in names:
        return True
    for n in names:
        py = _JSON_TYPES.get(n)
        if py is None:
            return True
        if isinstance(value, bool) and n in ("integer", "number"):
            continue  # bool is an int in Python, not in JSON schema
        if isinstance(value, py):
            return True
    return False


def validate_call(tool: Tool, args) -> list[str]:
    """Problems with a call, each a short sentence; [] if the call is valid."""
    if not isinstance(args, dict):
        return [f"arguments must be an object with named fields, got {type(args).__name__}"]
    problems = []
    for key in args:
        if key not in tool.inputs:
            problems.append(f"`{key}` is not an argument of `{tool.name}`")
    for key, spec in tool.inputs.items():
        if key not in args:
            if not is_optional(spec):
                problems.append(f"required argument `{key}` is missing")
            continue
        value = args[key]
        if not _type_ok(value, spec):
            problems.append(f"`{key}` must be {'|'.join(_type_names(spec))}, got {json.dumps(value)}")
            continue
        allowed = enum_values(spec)
        if allowed and value is not None and value not in allowed:
            problems.append(f"`{key}` must be one of {json.dumps(allowed)}, got {json.dumps(value)}")
    return problems


# --- provider errors --------------------------------------------------------------------------

_UNKNOWN_TOOL = re.compile(r"attempted to call tool '([^']+)' which was not in request\.tools")
_SCHEMA = re.compile(r"parameters for tool (\w+) did not match schema: errors: \[(.*?)\]", re.S)
_FAILED_GEN = re.compile(r"'failed_generation':\s*'(.*?)'\s*}", re.S)


def parse_provider_error(message: str) -> tuple[str, dict] | None:
    """Classify a provider HTTP 400 we can repair. None = not repairable (re-raise)."""
    if "Error code: 400" not in message:
        return None
    gen = _FAILED_GEN.search(message)
    detail = {"generation": gen.group(1)[:300] if gen else ""}
    if m := _UNKNOWN_TOOL.search(message):
        return WRONG_TOOL, {**detail, "tool": m.group(1)}
    if m := _SCHEMA.search(message):
        return WRONG_ARGUMENT, {**detail, "tool": m.group(1), "errors": m.group(2)[:300]}
    if "output_parse_failed" in message or "Tool choice is required" in message:
        return MALFORMED, detail
    return None


# --- feedback text ---------------------------------------------------------------------------

def already_done_note(mutating_calls: list[str]) -> str:
    if not mutating_calls:
        return ""
    listed = "; ".join(mutating_calls[-6:])
    return f"\nAlready done in this request (these changed state; do NOT repeat them): {listed}."


def feedback_wrong_tool(name: str, offered: list[str]) -> str:
    names = ", ".join(n for n in offered if n != "final_answer")
    return (
        f"There is no tool named `{name}`. To answer the user, call `final_answer` or reply in plain text. "
        f"Tools you can call now: {names}."
    )


def feedback_arguments(tool: Tool, problems: list[str]) -> str:
    return f"Invalid call to `{tool.name}`: " + "; ".join(problems) + f". Correct signature: {tool_signature(tool)}."


def feedback_malformed() -> str:
    return (
        "Your last reply could not be read as a tool call or an answer. Reply with exactly one valid tool "
        "call, or with a plain-text answer if the request is done."
    )
