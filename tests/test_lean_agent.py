"""Offline tests of C1 (agent/lean_agent.py) with a scripted model that records each request."""

from dataclasses import replace

from smolagents import ActionStep, TaskStep
from smolagents.memory import ToolCall
from smolagents.monitoring import Timing

from agent.bfcl_adapter import load_tasks
from agent.lean_agent import LeanOptions, LeanToolCallingAgent
from agent.retrieval.bm25 import tokenize
from agent.retrieval.tool_index import ToolIndex, split_preamble
from agent.runner import stream_task
from tests.test_runner import ScriptedModel, text_msg, tool_msg

TASK_100 = load_tasks(["multi_turn_base_100"])[0]  # TradingBot, 20 tools
PASS_SCRIPT = [
    tool_msg("get_stock_info", {"symbol": "NVDA"}),
    text_msg("NVDA is $220.34"),
    tool_msg("fund_account", {"amount": 2203.4}),
    text_msg("Funded"),
]


class RecordingModel(ScriptedModel):
    def __init__(self, script):
        super().__init__(script)
        self.requests = []

    def generate(self, messages, **kwargs):
        self.requests.append({"messages": messages, "tools": [t.name for t in kwargs.get("tools_to_call_from") or []]})
        return super().generate(messages, **kwargs)


def system_text(req):
    first = req["messages"][0]
    content = first.content if hasattr(first, "content") else first["content"]
    return content if isinstance(content, str) else " ".join(p.get("text", "") for p in content)


def test_tokenize_splits_camel_and_snake_case():
    assert tokenize("lockDoors get_stock_info") == ["lock", "door", "get", "stock", "info"]


def test_split_preamble():
    pre, spec = split_preamble("This tool belongs to X. Tool description: Do the thing.")
    assert pre == "This tool belongs to X." and spec == "Do the thing."
    assert split_preamble("plain") == ("", "plain")


def test_bm25_ranks_the_obvious_tool_first():
    from agent.bfcl_adapter import BFCLEnv

    index = ToolIndex(list(BFCLEnv(TASK_100).tools.values()))
    assert index.top_k("What is the current stock price of Nvidia?", 3)[0] == "get_stock_info"


def test_stock_runner_offers_every_tool_and_lists_them_in_prompt():
    model = RecordingModel(PASS_SCRIPT)
    events = list(stream_task(TASK_100, model))
    assert events[-1]["outcome"] == "pass"
    assert len(model.requests[0]["tools"]) == 21  # 20 + final_answer
    assert "fund_account:" in system_text(model.requests[0])


def test_c1_offers_top_k_plus_core_and_passes():
    model = RecordingModel(PASS_SCRIPT)
    events = list(stream_task(TASK_100, model, lean=LeanOptions(k=3)))
    done = events[-1]
    assert done["outcome"] == "pass"
    first = model.requests[0]
    assert "get_stock_info" in first["tools"] and "final_answer" in first["tools"]
    assert len(first["tools"]) < 21
    # tool docs not duplicated into the system prompt; API boilerplate stated once
    sp = system_text(first)
    assert "fund_account:" not in sp and sp.count("This tool belongs to the trading system") == 1
    steps = [e for e in events if e["type"] == "step"]
    assert all(e["tools_offered"] < 21 for e in steps)


def test_used_tools_stay_offered():
    model = RecordingModel(PASS_SCRIPT)
    list(stream_task(TASK_100, model, lean=LeanOptions(k=1, core_tools=False)))
    # turn 2 is about funding, but get_stock_info was used in turn 1 so it is still offered
    assert "get_stock_info" in model.requests[2]["tools"]


def test_retrieval_miss_is_added_and_step_retried():
    # raised inside model.generate, as Groq's 400 is; smolagents wraps it in AgentGenerationError
    miss = RuntimeError("Error code: 400 - attempted to call tool 'fund_account' which was not in request.tools")
    script = [miss, tool_msg("fund_account", {"amount": 1.0}), text_msg("done")]
    task = dict(TASK_100, question=[TASK_100["question"][1]], ground_truth=[TASK_100["ground_truth"][1]])
    model = RecordingModel(script)
    events = list(stream_task(task, model, lean=LeanOptions(k=1, core_tools=False)))
    assert "fund_account" in model.requests[1]["tools"]
    assert events[-1]["retrieval_misses"] == 1 and events[-1]["run_error"] is None


def test_unknown_tool_name_still_fatal():
    bad = RuntimeError("Error code: 400 - attempted to call tool 'answer' which was not in request.tools")
    events = list(stream_task(TASK_100, RecordingModel([bad]), lean=LeanOptions()))
    assert events[-1]["outcome"] == "provider_reject"


def _agent_with_history(options, n_steps=6, obs_chars=2000):
    from agent.bfcl_adapter import BFCLEnv

    agent = LeanToolCallingAgent(list(BFCLEnv(TASK_100).tools.values()), ScriptedModel([]), options)
    agent.memory.steps.append(TaskStep(task="do things"))
    for i in range(n_steps):
        agent.memory.steps.append(
            ActionStep(
                step_number=i + 1,
                timing=Timing(start_time=0.0, end_time=1.0),
                tool_calls=[ToolCall(name="get_stock_info", arguments={"symbol": "NVDA"}, id=f"c{i}")],
                observations="x" * obs_chars,
            )
        )
    agent.select_tools()
    return agent


def _size(messages):
    return sum(len(p.get("text", "")) for m in messages for p in (m.content or []) if isinstance(p, dict))


def test_history_keeps_last_steps_and_shortens_older_ones():
    full = _agent_with_history(replace(LeanOptions(), history_keep_steps=None, request_token_budget=None))
    kept2 = _agent_with_history(LeanOptions(history_keep_steps=2, request_token_budget=None))
    m_full, m_kept = full.write_memory_to_messages(), kept2.write_memory_to_messages()
    assert len(m_full) == len(m_kept)  # nothing dropped, only shortened
    assert _size(m_kept) < _size(m_full) - 4 * 1500  # 4 older observations cut to ~300 chars
    assert "x" * 2000 in m_kept[-1].content[0]["text"]  # the latest step is verbatim


def test_request_budget_tightens_history():
    agent = _agent_with_history(LeanOptions(history_keep_steps=6, request_token_budget=2500))
    assert agent._estimate_tokens(agent.write_memory_to_messages()) <= 2500


def test_compact_requires_single_listing():
    import pytest

    with pytest.raises(ValueError):
        LeanToolCallingAgent([], ScriptedModel([]), LeanOptions(single_tool_listing=False))
