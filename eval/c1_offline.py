"""C1 offline evaluation: tool-retrieval recall and prompt size, with zero LLM calls.

    python eval/c1_offline.py --tasks eval/tasks/dev.jsonl

For every turn of every task, the "needed" tools are those the BFCL ground truth calls in that
turn. A turn is *covered* at k if all of them are in the tools offered: the top-k for the query,
plus (with --sticky) the tools the ground truth called in earlier turns, approximating the agent
keeping tools it has already used. Run on the dev set only (tuning); never on the frozen sample.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.bfcl_adapter import BFCLEnv, load_tasks  # noqa: E402
from agent.retrieval.tool_index import ToolIndex  # noqa: E402

KS = (3, 5, 8, 10, 15)


def called_names(turn_calls: list[str]) -> set[str]:
    return {c.split("(", 1)[0] for c in turn_calls}


def turn_query(task: dict, turn: int, mode: str) -> str:
    texts = [" ".join(m["content"] for m in msgs) for msgs in task["question"]]
    if mode == "turn":
        return texts[turn]
    if mode == "turn+prev":
        return " ".join(texts[max(0, turn - 1) : turn + 1])
    raise ValueError(mode)


def evaluate(tasks: list[dict], mode: str, sticky: bool) -> dict:
    covered = {k: 0 for k in KS}
    recall = {k: 0.0 for k in KS}
    turns = 0
    for task in tasks:
        env = BFCLEnv(task)
        index = ToolIndex(list(env.tools.values()))
        used: set[str] = set()
        for t, gt_calls in enumerate(task["ground_truth"]):
            needed = called_names(gt_calls)
            if needed:
                turns += 1
                ranked = [n for n, _ in index.rank(turn_query(task, t, mode))]
                for k in KS:
                    offered = set(ranked[:k]) | (used if sticky else set())
                    covered[k] += needed <= offered
                    recall[k] += len(needed & offered) / len(needed)
            used |= needed
    return {
        "turns": turns,
        "covered": {k: covered[k] / turns for k in KS},
        "recall": {k: recall[k] / turns for k in KS},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=Path, default=ROOT / "eval" / "tasks" / "dev.jsonl")
    args = ap.parse_args()
    ids = [json.loads(l)["id"] for l in args.tasks.read_text(encoding="utf-8").splitlines() if l.strip()]
    if "frozen" in args.tasks.name:
        print("Refusing to tune on the frozen sample.")
        return 1
    tasks = load_tasks(ids)
    print(f"{len(tasks)} tasks from {args.tasks.name}; a turn is covered if ALL its ground-truth tools are offered\n")
    print("| Query | Sticky | Turns | " + " | ".join(f"covered@{k}" for k in KS) + " | " + " | ".join(f"recall@{k}" for k in KS) + " |")
    print("|---|---|---|" + "---|" * (2 * len(KS)))
    for mode in ("turn", "turn+prev"):
        for sticky in (False, True):
            r = evaluate(tasks, mode, sticky)
            print(
                f"| {mode} | {'yes' if sticky else 'no'} | {r['turns']} | "
                + " | ".join(f"{r['covered'][k]:.0%}" for k in KS)
                + " | "
                + " | ".join(f"{r['recall'][k]:.0%}" for k in KS)
                + " |"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
