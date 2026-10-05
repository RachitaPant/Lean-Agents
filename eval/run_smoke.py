"""Phase 1: run the stock smolagents ToolCallingAgent on a few BFCL multi-turn tasks and score
them with BFCL's checker. Phase 3 grows this into eval/run.py (configs, quota-aware resume).

Usage:
    python eval/run_smoke.py                      # the 3 dev smoke tasks
    python eval/run_smoke.py --ids multi_turn_base_3 --out eval/results/x.jsonl

The agent loop and turn protocol live in agent/runner.py (shared with the live demo).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.bfcl_adapter import load_tasks  # noqa: E402
from agent.runner import make_model, stream_task  # noqa: E402

DEV_SMOKE_IDS = ["multi_turn_base_3", "multi_turn_base_100", "multi_turn_base_17"]


def run_task(task: dict, model) -> dict:
    step_errors = []
    for event in stream_task(task, model):
        if event["type"] == "tool_call":
            print(f"  [turn {event['turn']}] {event['name']}({event['args']})")
        elif event["type"] == "step" and event["error"]:
            step_errors.append(event["error"])
        elif event["type"] == "run_error":
            print(f"  run_error ({event['kind']}): {event['message'][:200]}")
        elif event["type"] == "done":
            done = event
    return {
        "id": task["id"],
        "config": "stock+bfcl_turn_protocol",
        "model": model.model_id,
        **{k: v for k, v in done.items() if k not in ("type", "task_id")},
        "step_errors": step_errors,
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
                f"{rec['id']}: {rec['outcome']} llm_calls={rec['llm_calls']} "
                f"tokens={rec['prompt_tokens']}+{rec['completion_tokens']} {rec['latency_s']}s"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
