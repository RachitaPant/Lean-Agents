"""Offline checks of eval/bfcl_adapter.py against BFCL's own checker. No network, no LLM.

Replaying the ground-truth calls through our tool wrappers must score as valid on every
multi_turn_base task; if it doesn't, the adapter is changing behaviour somewhere.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from bfcl_adapter import BFCLEnv, format_call, load_tasks, parse_call, score  # noqa: E402

ALL_TASKS = load_tasks()


def replay_ground_truth(task):
    env = BFCLEnv(task)
    for turn in task["ground_truth"]:
        env.start_turn()
        for call in turn:
            env.call_ground_truth(call)
            env.end_step()
    env.end_step()
    return env


def test_all_base_tasks_loaded():
    assert len(ALL_TASKS) == 200


@pytest.mark.parametrize("task", ALL_TASKS, ids=lambda t: t["id"])
def test_ground_truth_replay_scores_valid(task):
    env = replay_ground_truth(task)
    result = score(task, env.calls)
    assert result["valid"], result.get("error_message")


def test_wrong_calls_score_invalid():
    task = load_tasks(["multi_turn_base_3"])[0]
    env = BFCLEnv(task)
    for _ in task["ground_truth"]:
        env.start_turn()
        env.call_ground_truth("pwd()")
        env.end_step()
    assert not score(task, env.calls)["valid"]


def test_empty_turn_scores_invalid():
    task = load_tasks(["multi_turn_base_100"])[0]
    calls = [[] for _ in task["ground_truth"]]
    assert not score(task, calls)["valid"]


def test_tool_schema_types_are_smolagents_compatible():
    task = load_tasks(["multi_turn_base_17"])[0]
    env = BFCLEnv(task)
    for tool in env.tools.values():
        for spec in tool.inputs.values():
            assert spec["type"] not in ("float", "dict", "tuple")


def test_optional_params_accept_null_in_json_schema():
    from smolagents.models import get_tool_json_schema

    env = BFCLEnv(load_tasks(["multi_turn_base_3"])[0])
    params = get_tool_json_schema(env.tools["find"])["function"]["parameters"]
    assert params["properties"]["path"]["type"] == ["string", "null"]
    assert "path" not in params["required"]
    # null means "use the default": the call runs and is logged without the arg
    env.start_turn()
    env.tools["find"](name="test", path=None)
    env.end_step()
    assert env.calls == [[["find(name='test')"]]]


def test_call_string_round_trip():
    s = format_call("mv", {"source": "a.txt", "destination": "b"})
    assert s == "mv(source='a.txt', destination='b')"
    assert parse_call(s, ["source", "destination"]) == ("mv", {"source": "a.txt", "destination": "b"})
    assert parse_call("sort('r.pdf')", ["file_name"]) == ("sort", {"file_name": "r.pdf"})
