"""Offline tests of agent/runner.py with a scripted fake model. No network."""

from smolagents.models import ChatMessage, ChatMessageToolCall, ChatMessageToolCallFunction
from smolagents.monitoring import TokenUsage

from agent.bfcl_adapter import load_tasks
from agent.runner import BFCLTurnModel, classify_error, stream_task


def tool_msg(name, args):
    return ChatMessage(
        role="assistant",
        content=None,
        tool_calls=[
            ChatMessageToolCall(
                id=f"call_{name}", type="function", function=ChatMessageToolCallFunction(name=name, arguments=args)
            )
        ],
        token_usage=TokenUsage(input_tokens=100, output_tokens=10),
    )


def text_msg(text):
    return ChatMessage(role="assistant", content=text, token_usage=TokenUsage(input_tokens=100, output_tokens=5))


class ScriptedModel(BFCLTurnModel):
    """Returns scripted replies in order; an Exception in the script is raised instead."""

    def __init__(self, script):
        super().__init__(model_id="scripted", api_base="http://localhost", api_key="test", tool_choice="auto")
        self.script = list(script)

    def generate(self, messages, **kwargs):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


TASK_100 = load_tasks(["multi_turn_base_100"])[0]
# ground truth: [["get_stock_info(symbol='NVDA')"], ['fund_account(amount=2203.4)']]


def run(script, task=TASK_100, **kw):
    return list(stream_task(task, ScriptedModel(script), **kw))


def test_correct_run_passes_and_text_reply_ends_turn():
    events = run([
        tool_msg("get_stock_info", {"symbol": "NVDA"}),
        text_msg("NVDA is at $220.34."),  # plain text → ends turn 0
        tool_msg("fund_account", {"amount": 2203.4}),
        tool_msg("final_answer", {"answer": "Funded."}),
    ])
    types = [e["type"] for e in events]
    assert types[0] == "run_start" and types[-1] == "done"
    assert types.count("turn_start") == 2 and types.count("turn_end") == 2
    done = events[-1]
    assert done["outcome"] == "pass" and done["success"]
    assert done["calls"] == [[["get_stock_info(symbol='NVDA')"]], [["fund_account(amount=2203.4)"]]]
    assert done["llm_calls"] == 4 and done["prompt_tokens"] == 400
    assert events[1]["user"].startswith("I'm contemplating")


def test_wrong_state_is_checker_fail():
    events = run([
        tool_msg("get_stock_info", {"symbol": "NVDA"}),
        text_msg("done"),
        tool_msg("fund_account", {"amount": 1.0}),
        text_msg("done"),
    ])
    assert events[-1]["outcome"] == "checker_fail"


def test_provider_400_ends_run_and_is_classified():
    err = RuntimeError("Error code: 400 - {'error': {'code': 'tool_use_failed'}}")
    events = run([tool_msg("get_stock_info", {"symbol": "NVDA"}), err])
    kinds = [e for e in events if e["type"] == "run_error"]
    assert len(kinds) == 1 and kinds[0]["kind"] == "provider_reject"
    done = events[-1]
    assert done["outcome"] == "provider_reject" and not done["success"]
    assert len(done["calls"]) == 2  # padded so the checker sees every turn


def test_deadline_interrupts_run():
    events = run([tool_msg("get_stock_info", {"symbol": "NVDA"})] * 5, deadline_s=0)
    assert events[-1]["outcome"] == "timeout"


def test_step_cap_fails_task():
    # 2 tool steps hit the cap; smolagents then makes one extra "final answer" call
    script = [tool_msg("get_stock_info", {"symbol": "NVDA"})] * 2 + [text_msg("final")]
    events = run(script, max_steps_per_turn=2)
    done = events[-1]
    assert done["hit_step_cap"] and done["outcome"] == "step_cap"
    assert [e["type"] for e in events].count("step") == 2  # the re-yielded step is not duplicated
    assert done["llm_calls"] == 3  # includes the extra summarise call


def test_classify_error():
    assert classify_error(Exception("Error code: 429 - rate limit")) == "rate_limited"
    assert classify_error(Exception("Error code: 413 - too large")) == "request_too_large"
    assert classify_error(Exception("Agent interrupted.")) == "timeout"
    assert classify_error(Exception("Error code: 503 - over capacity")) == "provider_unavailable"
    assert classify_error(Exception("Error while generating output: Connection error.")) == "provider_unavailable"
    assert classify_error(Exception("boom")) == "error"
