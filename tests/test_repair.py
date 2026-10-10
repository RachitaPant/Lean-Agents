"""Tests for C2 (agent/repair.py + its wiring in agent/lean_agent.py), from real failure messages."""

from dataclasses import replace

from agent import repair as c2
from agent.bfcl_adapter import BFCLEnv, load_tasks
from agent.runner import stream_task
from eval.configs import C1, C2, STOCK
from tests.test_lean_agent import RecordingModel
from tests.test_runner import text_msg, tool_msg

TASK_100 = load_tasks(["multi_turn_base_100"])[0]  # TradingBot: get_stock_info, then fund_account
TASK_50 = load_tasks(["multi_turn_base_50"])[0]  # VehicleControlAPI

# Provider messages as Groq returned them in Phases 1-2 (org id removed)
ANSWER_400 = (
    "Error code: 400 - {'error': {'message': \"Tool call validation failed: tool call validation failed: attempted "
    "to call tool 'answer' which was not in request.tools\", 'type': 'invalid_request_error', 'code': "
    "'tool_use_failed', 'failed_generation': '{\"name\": \"answer\", \"arguments\": {\"answer\": \"NVDA is $220\"}}'}}"
)
PARSE_400 = (
    "Error code: 400 - {'error': {'message': \"Parsing failed. The model generated output that could not be parsed.\", "
    "'type': 'invalid_request_error', 'code': 'output_parse_failed', 'failed_generation': 'We have the stock info'}}"
)
SCHEMA_400 = (
    "Error code: 400 - {'error': {'message': 'Tool call validation failed: tool call validation failed: parameters for "
    "tool find did not match schema: errors: [`/path`: expected string, but got null]', 'code': 'tool_use_failed'}}"
)


def tools(task):
    return BFCLEnv(task).tools


def messages_text(req):
    out = []
    for m in req["messages"]:
        content = m.content if hasattr(m, "content") else m["content"]
        out += [p.get("text", "") for p in content or [] if isinstance(p, dict)] if not isinstance(content, str) else [content]
    return "\n".join(out)


# --- pure helpers -------------------------------------------------------------------------------

def test_enum_from_bfcl_description_and_signature():
    start = tools(TASK_50)["startEngine"]
    assert c2.enum_values(start.inputs["ignitionMode"]) == ["START", "STOP"]
    assert c2.tool_signature(start) == 'startEngine(ignitionMode: string one of ["START", "STOP"])'


def test_validate_names_the_tool_and_problem():
    est = tools(TASK_50)["estimate_distance"]
    assert c2.validate_call(est, {"cityA": "94016", "cityB": "83214"}) == []
    problems = c2.validate_call(est, {"city": "SF", "cityB": "83214"})
    assert "`city` is not an argument of `estimate_distance`" in problems
    assert "required argument `cityA` is missing" in problems
    assert "cityA: string" in c2.feedback_arguments(est, problems)
    start = tools(TASK_50)["startEngine"]
    assert c2.validate_call(start, {"ignitionMode": "ON"}) == ['`ignitionMode` must be one of ["START", "STOP"], got "ON"']
    fund = tools(TASK_100)["fund_account"]
    assert c2.validate_call(fund, {"amount": "ten"}) == ['`amount` must be number, got "ten"']
    assert c2.validate_call(fund, {"amount": True}) != []  # a bool is not a number in JSON


def test_unwrap_invented_wrapper_only_when_not_a_real_parameter():
    watch = tools(TASK_100)["get_watchlist"]
    assert c2.unwrap_arguments(watch, {"arguments": {}}) == ({}, True)
    assert c2.unwrap_arguments(watch, {"args": {}}) == ({}, True)
    info = tools(TASK_100)["get_stock_info"]
    assert c2.unwrap_arguments(info, {"symbol": "NVDA"}) == ({"symbol": "NVDA"}, False)


def test_parse_provider_errors():
    assert c2.parse_provider_error(ANSWER_400)[0] == c2.WRONG_TOOL
    assert c2.parse_provider_error(ANSWER_400)[1]["tool"] == "answer"
    assert c2.parse_provider_error(PARSE_400)[0] == c2.MALFORMED
    kind, detail = c2.parse_provider_error(SCHEMA_400)
    assert kind == c2.WRONG_ARGUMENT and detail["tool"] == "find"
    assert c2.parse_provider_error("Error code: 413 - too large") is None


# --- wired into the agent -------------------------------------------------------------------------

def test_without_c2_an_invented_tool_kills_the_task():
    model = RecordingModel([tool_msg("get_stock_info", {"symbol": "NVDA"}), RuntimeError(ANSWER_400)])
    assert list(stream_task(TASK_100, model, lean=C1))[-1]["outcome"] == "provider_reject"


def test_c2_turns_an_invented_tool_into_feedback_and_the_task_passes():
    script = [
        tool_msg("get_stock_info", {"symbol": "NVDA"}),
        RuntimeError(ANSWER_400),
        text_msg("NVDA is $220.34"),
        tool_msg("fund_account", {"amount": 2203.4}),
        text_msg("Funded"),
    ]
    model = RecordingModel(script)
    done = list(stream_task(TASK_100, model, lean=replace(C1, repair=C2)))[-1]
    assert done["outcome"] == "pass"
    assert done["repairs"] == [{"category": "wrong_tool", "tool": "answer", "source": "provider"}]
    assert "There is no tool named `answer`" in messages_text(model.requests[2])


def test_c2_alone_works_on_the_stock_agent():
    script = [RuntimeError(PARSE_400), tool_msg("get_stock_info", {"symbol": "NVDA"}), text_msg("ok"),
              tool_msg("fund_account", {"amount": 2203.4}), text_msg("ok")]
    model = RecordingModel(script)
    done = list(stream_task(TASK_100, model, lean=replace(STOCK, repair=C2)))[-1]
    assert done["outcome"] == "pass" and done["repairs"][0]["category"] == "malformed_output"
    assert len(model.requests[0]["tools"]) == 21  # stock: every tool offered


def test_bad_argument_gets_signature_and_already_done_note():
    script = [
        tool_msg("get_stock_info", {"symbol": "NVDA"}), text_msg("ok"),
        tool_msg("fund_account", {"amount": 2203.4}),  # succeeds: changes state
        tool_msg("get_account_info", {"account": "me"}),  # invalid: no such argument
        text_msg("done"),
    ]
    model = RecordingModel(script)
    done = list(stream_task(TASK_100, model, lean=replace(C1, repair=C2)))[-1]
    seen = messages_text(model.requests[-1])
    assert "`account` is not an argument of `get_account_info`" in seen
    assert "Correct signature: get_account_info()" in seen
    assert "do NOT repeat them): fund_account(amount=2203.4)" in seen
    assert done["outcome"] == "pass" and done["repairs"][0]["category"] == "wrong_argument"


def test_wrapper_is_unwrapped_and_call_succeeds():
    script = [tool_msg("get_watchlist", {"arguments": {}}), text_msg("ok")]
    task = dict(TASK_100, question=[TASK_100["question"][0]], ground_truth=[["get_watchlist()"]])
    done = list(stream_task(task, RecordingModel(script), lean=replace(C1, repair=C2)))[-1]
    assert done["calls"] == [[["get_watchlist()"]]]
    assert done["repairs"] == [{"category": "wrapper_unwrapped", "tool": "get_watchlist", "source": "client"}]


def test_provider_repairs_are_capped_per_turn():
    script = [RuntimeError(ANSWER_400)] * 3
    opts = replace(C1, repair=replace(C2, max_repairs_per_turn=2))
    done = list(stream_task(TASK_100, RecordingModel(script), lean=opts))[-1]
    assert done["outcome"] == "provider_reject" and len(done["repairs"]) == 2


def test_mutations_tracked_per_turn():
    env = BFCLEnv(TASK_100)
    env.start_turn()
    env.call_ground_truth("get_stock_info(symbol='NVDA')")
    assert env.mutations_this_turn() == []
    env.call_ground_truth("fund_account(amount=10.0)")
    assert env.mutations_this_turn() == ["fund_account(amount=10.0)"]
    env.start_turn()
    assert env.mutations_this_turn() == []
