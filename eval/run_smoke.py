"""Phase 1: run the stock smolagents ToolCallingAgent on a few BFCL multi-turn tasks and score
them with BFCL's checker. Phase 3 grows this into eval/run.py (configs, quota-aware resume).

Usage:
    python eval/run_smoke.py                      # the 3 dev smoke tasks
    python eval/run_smoke.py --ids multi_turn_base_3 --out eval/results/x.jsonl

Turn semantics: each BFCL user turn is one `agent.run(..., reset=False)`, capped at 20 steps
(BFCL's limit; hitting it fails the task). A turn ends when the agent calls `final_answer` or,
as in BFCL's own protocol, replies with plain text and no tool call. That second rule needs
`tool_choice="auto"`: with smolagents' default "required", Groq rejects any text-only reply with
HTTP 400 and the whole task dies (seen on all 3 smoke tasks; see docs/ARCHITECTURE_NOTES.md).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from smolagents import ActionStep, OpenAIServerModel, ToolCallingAgent
from smolagents.models import ChatMessage, ChatMessageToolCall, ChatMessageToolCallFunction

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bfcl_adapter import BFCLEnv, load_tasks, score  # noqa: E402

DEV_SMOKE_IDS = ["multi_turn_base_3", "multi_turn_base_100", "multi_turn_base_17"]
MAX_STEPS_PER_TURN = 20  # BFCL's MAXIMUM_STEP_LIMIT


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


def make_model() -> OpenAIServerModel:
    return BFCLTurnModel(
        model_id=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        api_base=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        api_key=os.environ["GROQ_API_KEY"],
        tool_choice="auto",
    )


def run_task(task: dict, model) -> dict:
    env = BFCLEnv(task)
    agent = ToolCallingAgent(
        tools=list(env.tools.values()),
        model=model,
        max_steps=MAX_STEPS_PER_TURN,
        max_tool_threads=1,  # BFCL calls are stateful (cd then ls): keep them sequential
        step_callbacks=[env.end_step],
        verbosity_level=1,
    )
    hit_step_cap = False
    error = None
    t0 = time.time()
    try:
        for turn_idx, messages in enumerate(task["question"]):
            env.start_turn()
            user_text = "\n".join(m["content"] for m in messages if m["role"] == "user")
            steps_before = len([s for s in agent.memory.steps if isinstance(s, ActionStep)])
            agent.run(user_text, reset=(turn_idx == 0), max_steps=MAX_STEPS_PER_TURN)
            env.end_step()
            steps_now = len([s for s in agent.memory.steps if isinstance(s, ActionStep)])
            if steps_now - steps_before >= MAX_STEPS_PER_TURN:
                hit_step_cap = True
    except Exception as e:  # provider errors etc.: record, score what we have
        error = f"{type(e).__name__}: {e}"
        while len(env.calls) < len(task["ground_truth"]):
            env.calls.append([])
    latency = time.time() - t0

    action_steps = [s for s in agent.memory.steps if isinstance(s, ActionStep)]
    prompt_tokens = sum(s.token_usage.input_tokens for s in action_steps if s.token_usage)
    completion_tokens = sum(s.token_usage.output_tokens for s in action_steps if s.token_usage)
    step_errors = [str(s.error) for s in action_steps if s.error]

    result = score(task, env.calls)
    success = bool(result["valid"]) and not hit_step_cap and error is None
    return {
        "id": task["id"],
        "config": "stock+bfcl_turn_protocol",
        "model": model.model_id,
        "success": success,
        "checker": {k: v for k, v in result.items() if k in ("valid", "error_type", "error_message")},
        "hit_step_cap": hit_step_cap,
        "run_error": error,
        "llm_calls": len(action_steps),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "step_errors": step_errors,
        "latency_s": round(latency, 1),
        "calls": env.calls,
        "ground_truth": task["ground_truth"],
    }


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="+", default=DEV_SMOKE_IDS)
    ap.add_argument("--out", default="eval/results/phase1_smoke.jsonl")
    args = ap.parse_args()

    model = make_model()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        for task in load_tasks(args.ids):
            rec = run_task(task, model)
            f.write(json.dumps(rec) + "\n")
            f.flush()
            print(
                f"{rec['id']}: success={rec['success']} llm_calls={rec['llm_calls']} "
                f"tokens={rec['prompt_tokens']}+{rec['completion_tokens']} {rec['latency_s']}s "
                f"{rec['checker'].get('error_type', '')}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
