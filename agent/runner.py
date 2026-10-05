"""Run one BFCL multi-turn task with a smolagents ToolCallingAgent and stream trace events.

Shared by the live demo (api/index.py) and the eval scripts, so both run the same code path.

Turn semantics: each BFCL user turn is one `agent.run(..., reset=False)`, capped at
`max_steps_per_turn` (BFCL's limit is 20; hitting it fails the task). A turn ends when the agent
calls `final_answer` or, as in BFCL's own protocol, replies with plain text and no tool call.
That second rule needs `tool_choice="auto"`: with smolagents' default "required", Groq rejects
any text-only reply with HTTP 400 and the whole task dies (see docs/ARCHITECTURE_NOTES.md).

Events (plain dicts, JSON-serialisable), in order:
    run_start, then per turn: turn_start, (tool_call, tool_result)*, step ..., turn_end;
    run_error (at most once, ends the run early), and always a final `done` with the score.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

from smolagents import ActionStep, FinalAnswerStep, OpenAIServerModel, ToolCallingAgent
from smolagents.agents import ToolOutput
from smolagents.memory import ToolCall
from smolagents.models import ChatMessage, ChatMessageToolCall, ChatMessageToolCallFunction

from agent.bfcl_adapter import BFCLEnv, score

BFCL_MAX_STEPS_PER_TURN = 20
MAX_OBSERVATION_CHARS = 2000


class BFCLTurnModel(OpenAIServerModel):
    """OpenAI-compatible model where a text-only reply ends the turn (BFCL protocol).

    smolagents only ends a run on a `final_answer` tool call, so a plain-text reply is turned
    into one. Everything else (prompts, tool schemas, loop) is stock smolagents.
    """

    def parse_tool_calls(self, message: ChatMessage) -> ChatMessage:
        if not message.tool_calls:
            message.tool_calls = [
                ChatMessageToolCall(
                    id="text_reply",
                    type="function",
                    function=ChatMessageToolCallFunction(
                        name="final_answer", arguments={"answer": message.content or ""}
                    ),
                )
            ]
        return super().parse_tool_calls(message)


def make_model(model_id: str | None = None) -> BFCLTurnModel:
    return BFCLTurnModel(
        model_id=model_id or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        api_base=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        api_key=os.environ["GROQ_API_KEY"],
        tool_choice="auto",
    )


def classify_error(e: BaseException) -> str:
    """Bucket a run-ending error into an outcome category (see PROJECT_PLAN Phase 3)."""
    text = str(e)
    if "interrupted" in text.lower():
        return "timeout"
    if "Error code: 429" in text:
        return "rate_limited"
    if "Error code: 413" in text:
        return "request_too_large"
    if "Error code: 400" in text:
        return "provider_reject"
    return "error"


def _truncate(text: str, limit: int = MAX_OBSERVATION_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + f"... [{len(text) - limit} more chars]"


def stream_task(
    task: dict,
    model,
    max_steps_per_turn: int = BFCL_MAX_STEPS_PER_TURN,
    deadline_s: float | None = None,
) -> Iterator[dict]:
    """Run `task` turn by turn, yielding trace events. Never raises for agent/provider errors."""
    env = BFCLEnv(task)
    agent = ToolCallingAgent(
        tools=list(env.tools.values()),
        model=model,
        max_steps=max_steps_per_turn,
        max_tool_threads=1,  # BFCL calls are stateful (cd then ls): keep them sequential
        step_callbacks=[env.end_step],
        verbosity_level=0,
    )
    t0 = time.time()
    hit_step_cap = False
    run_error = None

    yield {
        "type": "run_start",
        "task_id": task["id"],
        "model": model.model_id,
        "turns": len(task["question"]),
        "tools": len(env.tools),
    }
    try:
        for turn_idx, messages in enumerate(task["question"]):
            env.start_turn()
            user_text = "\n".join(m["content"] for m in messages if m["role"] == "user")
            yield {"type": "turn_start", "turn": turn_idx, "user": user_text}
            steps_in_turn = 0
            seen_steps: set[int] = set()  # smolagents re-yields the last step when the cap is hit
            final_answer = None
            for item in agent.run(
                user_text, stream=True, reset=(turn_idx == 0), max_steps=max_steps_per_turn
            ):
                if isinstance(item, ToolCall) and item.name != "final_answer":
                    yield {"type": "tool_call", "turn": turn_idx, "name": item.name, "args": item.arguments}
                elif isinstance(item, ToolOutput) and not item.is_final_answer:
                    yield {
                        "type": "tool_result",
                        "turn": turn_idx,
                        "name": item.tool_call.name,
                        "observation": _truncate(item.observation or ""),
                    }
                elif isinstance(item, ActionStep) and id(item) not in seen_steps:
                    seen_steps.add(id(item))
                    steps_in_turn += 1
                    usage = item.token_usage
                    yield {
                        "type": "step",
                        "turn": turn_idx,
                        "step": item.step_number,
                        "prompt_tokens": usage.input_tokens if usage else 0,
                        "completion_tokens": usage.output_tokens if usage else 0,
                        "duration_s": round(item.timing.duration or 0, 2) if item.timing else None,
                        "error": _truncate(str(item.error), 500) if item.error else None,
                    }
                    if deadline_s is not None and time.time() - t0 > deadline_s:
                        agent.interrupt()  # raises "Agent interrupted" before the next step
                elif isinstance(item, FinalAnswerStep):
                    final_answer = item.output
            env.end_step()
            yield {"type": "turn_end", "turn": turn_idx, "answer": _truncate(str(final_answer or ""), 1000)}
            if steps_in_turn >= max_steps_per_turn:
                # BFCL force-quits here and fails the whole task: stop instead of spending quota.
                hit_step_cap = True
                break
    except Exception as e:  # provider errors, interrupts: stop the run, still score it
        run_error = {"kind": classify_error(e), "message": _truncate(str(e), 1000)}
        yield {"type": "run_error", **run_error}
    env.end_step()
    while len(env.calls) < len(task["ground_truth"]):
        env.calls.append([])

    # Totals from memory: it also holds the extra "summarise" call smolagents makes at the step cap,
    # which is never yielded as an event.
    action_steps = [s for s in agent.memory.steps if isinstance(s, ActionStep)]
    totals = {
        "llm_calls": len(action_steps),
        "prompt_tokens": sum(s.token_usage.input_tokens for s in action_steps if s.token_usage),
        "completion_tokens": sum(s.token_usage.output_tokens for s in action_steps if s.token_usage),
    }

    result = score(task, env.calls)
    if result["valid"] and not hit_step_cap and run_error is None:
        outcome = "pass"
    elif run_error is not None:
        outcome = run_error["kind"]
    elif hit_step_cap:
        outcome = "step_cap"
    else:
        outcome = "checker_fail"
    yield {
        "type": "done",
        "task_id": task["id"],
        "success": outcome == "pass",
        "outcome": outcome,
        "checker": {k: v for k, v in result.items() if k in ("valid", "error_type", "error_message")},
        "hit_step_cap": hit_step_cap,
        "run_error": run_error,
        "latency_s": round(time.time() - t0, 1),
        "calls": env.calls,
        **totals,
    }
