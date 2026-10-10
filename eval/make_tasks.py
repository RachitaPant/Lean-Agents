"""Draw evaluation task samples from BFCL multi_turn_base, reproducibly.

    python eval/make_tasks.py pilot  --n 10 --seed 1
    python eval/make_tasks.py dev    --n 30 --seed 3      # for tuning contributions (C1 k, retriever, ...)
    python eval/make_tasks.py frozen --n 50 --seed 2      # after the pilot; excludes pilot + dev tasks

Hygiene rules (CLAUDE.md, PROJECT_PLAN Phase 3):
  - never sample the Phase 1 dev smoke tasks or the live-demo presets;
  - the frozen sample is disjoint from the pilot and the dev set, and is never tuned on;
  - all tuning (retriever choice, k, thresholds) happens on the dev set only;
  - sampling is stratified by API group (the task's set of involved classes), so the sample
    keeps the benchmark's domain mix.
An existing output file is never overwritten (pass --force only if it was never used).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.bfcl_adapter import load_tasks  # noqa: E402

TASKS_DIR = ROOT / "eval" / "tasks"
DEV_SMOKE = {"multi_turn_base_3", "multi_turn_base_17", "multi_turn_base_100"}
DEMO_PRESETS = {"multi_turn_base_50", "multi_turn_base_100", "multi_turn_base_132", "multi_turn_base_182"}
EXCLUDED = DEV_SMOKE | DEMO_PRESETS


def group_of(task: dict) -> str:
    return "+".join(sorted(task["involved_classes"]))


def stratified_sample(tasks: list[dict], n: int, seed: int) -> list[dict]:
    """Proportional allocation per group (largest remainder), random within each group."""
    rng = random.Random(seed)
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in sorted(tasks, key=lambda t: t["id"]):
        groups[group_of(t)].append(t)
    total = len(tasks)
    quotas = {g: n * len(ts) / total for g, ts in groups.items()}
    alloc = {g: int(q) for g, q in quotas.items()}
    for g in sorted(quotas, key=lambda g: (quotas[g] - alloc[g], g), reverse=True)[: n - sum(alloc.values())]:
        alloc[g] += 1
    picked = []
    for g in sorted(groups):
        picked += rng.sample(groups[g], alloc[g])
    rng.shuffle(picked)
    return picked


def read_ids(path: Path) -> set[str]:
    return {json.loads(l)["id"] for l in path.read_text(encoding="utf-8").splitlines() if l.strip()} if path.exists() else set()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["pilot", "dev", "frozen"])
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    out = TASKS_DIR / {"pilot": "pilot.jsonl", "dev": "dev.jsonl", "frozen": "frozen_sample.jsonl"}[args.kind]
    if out.exists() and not args.force:
        print(f"{out.name} already exists; refusing to overwrite (it may already have been used).")
        return 1
    excluded = set(EXCLUDED)
    if args.kind in ("dev", "frozen"):
        excluded |= read_ids(TASKS_DIR / "pilot.jsonl")
    if args.kind == "frozen":
        excluded |= read_ids(TASKS_DIR / "dev.jsonl")
    pool = [t for t in load_tasks() if t["id"] not in excluded]
    sample = stratified_sample(pool, args.n, args.seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for t in sample:
            f.write(json.dumps({"id": t["id"], "group": group_of(t), "turns": len(t["question"])}) + "\n")
    print(f"wrote {len(sample)} tasks to {out.relative_to(ROOT)} (pool {len(pool)}, seed {args.seed})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
