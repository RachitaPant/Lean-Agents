"""Build agent/retrieval/core_tools.json: per-API tools that C1 always offers.

    python eval/build_core_tools.py            # learns from eval/tasks/dev.jsonl only

A tool is "core" for an API if the BFCL ground truth uses it in at least THRESHOLD of the dev
tasks involving that API. These are mostly prerequisites users never mention (cd, logins,
pressBrakePedal), which lexical retrieval cannot find. Threshold chosen on dev with
leave-one-task-out cross-validation (docs/PHASE_LOG.md, Phase 4). Never built from the frozen sample.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.bfcl_adapter import load_func_docs, load_tasks  # noqa: E402
from agent.retrieval.core_tools import CORE_TOOLS_PATH  # noqa: E402

THRESHOLD = 0.5
DEV = ROOT / "eval" / "tasks" / "dev.jsonl"
CLASSES = ["GorillaFileSystem", "MathAPI", "MessageAPI", "TwitterAPI", "TicketAPI", "TradingBot", "TravelAPI", "VehicleControlAPI"]


def build(tasks: list[dict], threshold: float) -> dict[str, list[str]]:
    owner = {d["name"]: c for c in CLASSES for d in load_func_docs(c)}
    class_tasks: Counter = Counter()
    usage: dict[str, Counter] = defaultdict(Counter)
    for t in tasks:
        used = {call.split("(", 1)[0] for turn in t["ground_truth"] for call in turn}
        for c in t["involved_classes"]:
            class_tasks[c] += 1
            usage[c].update(n for n in used if owner.get(n) == c)
    return {
        c: sorted(n for n, f in usage[c].items() if f / class_tasks[c] >= threshold)
        for c in sorted(class_tasks)
    }


def main() -> int:
    ids = [json.loads(l)["id"] for l in DEV.read_text(encoding="utf-8").splitlines() if l.strip()]
    core = build(load_tasks(ids), THRESHOLD)
    CORE_TOOLS_PATH.write_text(
        json.dumps({"source": "eval/tasks/dev.jsonl", "threshold": THRESHOLD, "classes": core}, indent=2) + "\n",
        encoding="utf-8",
    )
    for c, names in core.items():
        print(f"{c}: {', '.join(names) or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
