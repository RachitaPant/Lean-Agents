"""Summarise evaluation results: success with 95% bootstrap CI, outcomes, token/latency stats.

    python eval/analyze.py eval/results/pilot/baseline.jsonl
    python eval/analyze.py eval/results/frozen_sample/*.jsonl --md eval/results/frozen_sample/summary.md --plots eval/results/frozen_sample/plots

Only *final* records count (see eval/run.py). If a (task, repeat) has several final records,
the last one wins. Infrastructure failures that stayed final after retries
(provider_unavailable, rate_limited) count as failures but are reported separately.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

INFRA_OUTCOMES = {"provider_unavailable", "rate_limited", "rate_limited_daily"}
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 0


def load_final(path: Path) -> list[dict]:
    latest: dict[tuple[str, int], dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("final"):
                latest[(r["id"], r["repeat"])] = r
    return list(latest.values())


def bootstrap_ci(values: list[float], resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED):
    """Percentile bootstrap 95% CI of the mean."""
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(resamples))
    return means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1]


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else float("nan")


def summarise(records: list[dict]) -> dict:
    """Per-config summary. With repeats, success is averaged per task first (so each task
    weighs the same), and the bootstrap resamples tasks."""
    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_task[r["id"]].append(r)
    per_task_success = [sum(r["success"] for r in rs) / len(rs) for rs in by_task.values()]
    tokens = [r["prompt_tokens"] + r["completion_tokens"] for r in records]
    lo, hi = bootstrap_ci(per_task_success)
    return {
        "tasks": len(by_task),
        "records": len(records),
        "success_rate": sum(per_task_success) / len(per_task_success) if per_task_success else float("nan"),
        "ci95": (lo, hi),
        "outcomes": Counter(r["outcome"] for r in records),
        "infra_failures": sum(r["outcome"] in INFRA_OUTCOMES for r in records),
        "tokens_mean": statistics.mean(tokens) if tokens else float("nan"),
        "tokens_median": statistics.median(tokens) if tokens else float("nan"),
        "tokens_p90": pct(tokens, 0.9),
        "tokens_max": max(tokens) if tokens else float("nan"),
        "prompt_tokens_per_call": (
            sum(r["prompt_tokens"] for r in records) / max(1, sum(r["llm_calls"] for r in records))
        ),
        "llm_calls_mean": statistics.mean(r["llm_calls"] for r in records) if records else float("nan"),
        "latency_median_s": statistics.median(r["latency_s"] for r in records) if records else float("nan"),
        "invalid_calls_total": sum(r.get("invalid_tool_calls", 0) for r in records),
        "invalid_calls_per_task": (
            statistics.mean(r.get("invalid_tool_calls", 0) for r in records) if records else float("nan")
        ),
        "repeat_agreement": repeat_agreement(by_task),
        # C2: invalid calls caught and fed back, by category; "recovered" = the task still passed
        "repairs": Counter(x["category"] for r in records for x in r.get("repairs") or []),
        "tasks_repaired": sum(bool(r.get("repairs")) for r in records),
        "tasks_repaired_passed": sum(bool(r.get("repairs")) and r["success"] for r in records),
    }


def repeat_agreement(by_task: dict[str, list[dict]]):
    """Share of repeated tasks whose success was identical across all repeats (noise check)."""
    repeated = [rs for rs in by_task.values() if len(rs) > 1]
    if not repeated:
        return None
    same = sum(len({r["success"] for r in rs}) == 1 for rs in repeated)
    return {"tasks": len(repeated), "agree": same, "rate": same / len(repeated)}


def to_markdown(summaries: dict[str, dict]) -> str:
    lines = [
        "| Config | Tasks | Success | 95% CI | Mean tokens/task | Median | p90 | Prompt tokens/call | LLM calls/task | Invalid calls/task | Median latency |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, s in summaries.items():
        lo, hi = s["ci95"]
        lines.append(
            f"| {name} | {s['tasks']} | {s['success_rate']:.1%} | {lo:.1%}–{hi:.1%} | {s['tokens_mean']:,.0f} | "
            f"{s['tokens_median']:,.0f} | {s['tokens_p90']:,.0f} | {s['prompt_tokens_per_call']:,.0f} | "
            f"{s['llm_calls_mean']:.1f} | {s['invalid_calls_per_task']:.2f} | {s['latency_median_s']:.0f} s |"
        )
    lines += ["", "**Outcomes**", ""]
    for name, s in summaries.items():
        parts = ", ".join(f"{k}: {v}" for k, v in s["outcomes"].most_common())
        lines.append(f"- {name}: {parts} (infra failures: {s['infra_failures']})")
        if s["repairs"]:
            cats = ", ".join(f"{k}: {v}" for k, v in s["repairs"].most_common())
            lines.append(
                f"  - repairs (C2): {cats}; {s['tasks_repaired']} tasks needed a repair, "
                f"{s['tasks_repaired_passed']} of them still passed"
            )
        if s["repeat_agreement"]:
            a = s["repeat_agreement"]
            lines.append(f"  - repeat agreement: {a['agree']}/{a['tasks']} tasks ({a['rate']:.0%}) same result across repeats")
    return "\n".join(lines) + "\n"


def plot(all_records: dict[str, list[dict]], out_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    fig, ax = plt.subplots(figsize=(7, 4))
    for name, recs in all_records.items():
        ax.hist([r["prompt_tokens"] + r["completion_tokens"] for r in recs], bins=15, alpha=0.6, label=name)
    ax.set_xlabel("tokens per task")
    ax.set_ylabel("tasks")
    ax.set_title("Tokens per task")
    ax.legend()
    fig.tight_layout()
    paths.append(out_dir / "tokens_per_task.png")
    fig.savefig(paths[-1], dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    outcomes = sorted({r["outcome"] for recs in all_records.values() for r in recs})
    width = 0.8 / max(1, len(all_records))
    for i, (name, recs) in enumerate(all_records.items()):
        c = Counter(r["outcome"] for r in recs)
        ax.bar([j + i * width for j in range(len(outcomes))], [c[o] for o in outcomes], width, label=name)
    ax.set_xticks([j + width * (len(all_records) - 1) / 2 for j in range(len(outcomes))], outcomes, rotation=20)
    ax.set_ylabel("tasks")
    ax.set_title("Outcomes")
    ax.legend()
    fig.tight_layout()
    paths.append(out_dir / "outcomes.png")
    fig.savefig(paths[-1], dpi=120)
    plt.close(fig)
    return paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+", type=Path, help="eval/results/<tasks>/<config>.jsonl files")
    ap.add_argument("--md", type=Path, help="also write the markdown summary here")
    ap.add_argument("--plots", type=Path, help="directory for PNG plots")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console default is cp1252

    all_records = {p.stem: load_final(p) for p in args.results}
    summaries = {name: summarise(recs) for name, recs in all_records.items() if recs}
    md = to_markdown(summaries)
    print(md)
    if args.md:
        args.md.write_text(md, encoding="utf-8")
    if args.plots:
        for p in plot(all_records, args.plots):
            print(f"plot: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
