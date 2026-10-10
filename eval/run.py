"""Evaluation runner: one config over a task file, resumable and quota-aware.

    python eval/run.py --config baseline --tasks eval/tasks/pilot.jsonl
    python eval/run.py --config baseline --tasks eval/tasks/pilot.jsonl --repeats 2 --limit 5
    python eval/run.py ... --wait-on-quota     # sleep through Groq's daily limit and continue

Results are appended to eval/results/<tasks stem>/<config>.jsonl, one record per attempt.
A record is *final* when it counts towards results. Infrastructure failures are not final:
  - daily quota exhausted (429 tokens/requests per day): stop (or wait) and resume later;
  - per-minute 429 or provider 5xx: retried up to MAX_INFRA_ATTEMPTS, then final.
On restart, (task, repeat) pairs that already have a final record are skipped.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.bfcl_adapter import load_tasks  # noqa: E402
from agent.runner import stream_task  # noqa: E402
from dataclasses import replace  # noqa: E402

from eval.configs import CONFIGS, Config  # noqa: E402

HARNESS_VERSION = 1
MAX_INFRA_ATTEMPTS = 3  # provider 5xx only; per-minute 429s are already retried by openai + smolagents
INFRA_RETRY_SLEEP_S = 60
# Groq's daily limit is a rolling window: the 429's "try again in Xm" frees room for ONE request,
# not a whole task, so waking at the hint just burns ~7K tokens and fails again (seen in the
# pilot). Wait at least this long so a task's worth of quota (~50K tokens) has freed up.
DAILY_QUOTA_MIN_SLEEP_S = 6 * 3600
INVALID_CALL_ERRORS = {"AgentToolCallError", "AgentToolExecutionError", "AgentParsingError"}

EXIT_DONE, EXIT_QUOTA = 0, 3


def git_commit() -> str:
    try:
        head = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "agent", "eval/*.py"], cwd=ROOT, text=True)
        return head + ("-dirty" if dirty.strip() else "")
    except Exception:
        return "unknown"


def read_task_ids(path: Path) -> list[str]:
    return [json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def results_path(tasks_file: Path, config: str) -> Path:
    return ROOT / "eval" / "results" / tasks_file.stem / f"{config}.jsonl"


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def is_daily_quota(message: str) -> bool:
    m = message.lower()
    return "per day" in m or "(tpd)" in m or "(rpd)" in m


def parse_retry_after_s(message: str) -> float | None:
    """Groq 429 text: '... Please try again in 7m32.5s.' (also '1h2m3s', '45.1s', '850ms')."""
    m = re.search(r"try again in\s+((?:\d+h)?(?:\d+m(?!s))?(?:[\d.]+s)?(?:[\d.]+ms)?)", message)
    if not m or not m.group(1):
        return None
    total = 0.0
    for value, unit in re.findall(r"([\d.]+)(h|ms|m|s)", m.group(1)):
        total += float(value) * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[unit]
    return total


def run_once(task: dict, config: Config, model, log=print) -> dict:
    """One attempt at one task. Returns the record fields produced by the runner."""
    step_errors, invalid_calls = [], 0
    done = {}
    for event in stream_task(task, model, max_steps_per_turn=config.max_steps_per_turn, lean=config.lean):
        if event["type"] == "step":  # progress: free-tier steps can be a minute apart
            log(f"    turn {event['turn']} step {event['step']}: {event['prompt_tokens']} prompt tokens"
                f"{' error=' + event['error_type'] if event['error'] else ''}")
        if event["type"] == "step" and event["error"]:
            step_errors.append({"type": event["error_type"], "message": event["error"]})
            if event["error_type"] in INVALID_CALL_ERRORS:
                invalid_calls += 1
        elif event["type"] == "done":
            done = event
    if done.get("outcome") == "provider_reject":
        invalid_calls += 1  # the provider rejected a malformed/unknown tool call
    return {
        **{k: v for k, v in done.items() if k not in ("type", "task_id")},
        "invalid_tool_calls": invalid_calls,
        "step_errors": step_errors,
    }


def run(
    config: Config,
    tasks_file: Path,
    out: Path,
    repeats: int = 1,
    limit: int | None = None,
    wait_on_quota: bool = False,
    retry_outcomes: frozenset[str] = frozenset(),
    model_factory=None,
    sleep=time.sleep,
    log=print,
) -> int:
    model_factory = model_factory or config.make_model
    ids = read_task_ids(tasks_file)[:limit] if limit else read_task_ids(tasks_file)
    tasks = {t["id"]: t for t in load_tasks(ids)}
    out.parent.mkdir(parents=True, exist_ok=True)

    records = load_records(out)
    # retry_outcomes: re-run tasks whose final record has one of these outcomes, e.g. "error"
    # records finalised before a classifier fix (the old record stays; analyze uses the latest)
    latest = {(r["id"], r["repeat"]): r for r in records if r["final"]}
    final = {k for k, r in latest.items() if r["outcome"] not in retry_outcomes}
    attempts: dict[tuple[str, int], int] = {}
    for r in records:
        if not r["final"] and r.get("outcome") != "rate_limited_daily":
            attempts[(r["id"], r["repeat"])] = attempts.get((r["id"], r["repeat"]), 0) + 1

    commit = git_commit()
    todo = [(tid, rep) for rep in range(repeats) for tid in ids if (tid, rep) not in final]
    log(f"{config.name}: {len(todo)} to run, {len(final)} already final -> {out}")

    for tid, rep in todo:
        while True:
            started = datetime.now(timezone.utc)
            result = run_once(tasks[tid], config, model_factory(), log=log)
            key = (tid, rep)
            outcome = result["outcome"]
            message = (result.get("run_error") or {}).get("message", "")
            daily = outcome == "rate_limited" and is_daily_quota(message)
            # A per-minute 429 that survived the client's and smolagents' own retries means the
            # request barely fits the TPM window: re-running the whole task won't help, so it is
            # final (reported as rate_limited, separate from model failures).
            infra = outcome == "provider_unavailable" or daily
            if daily:
                outcome = result["outcome"] = "rate_limited_daily"
            attempts[key] = attempts.get(key, 0) + (1 if infra and not daily else 0)
            is_final = not infra or (not daily and attempts[key] >= MAX_INFRA_ATTEMPTS)
            record = {
                "id": tid,
                "repeat": rep,
                "config": config.name,
                "final": is_final,
                **result,
                "config_detail": config.to_dict(),
                "git_commit": commit,
                "harness_version": HARNESS_VERSION,
                "started_at": started.isoformat(timespec="seconds"),
            }
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
            log(
                f"  {tid} r{rep}: {outcome}{'' if is_final else ' (not final)'} calls={result['llm_calls']} "
                f"tokens={result['prompt_tokens']}+{result['completion_tokens']} {result['latency_s']}s"
            )
            if is_final:
                break
            if daily:
                wait = parse_retry_after_s(message)
                if not wait_on_quota:
                    log(f"Daily quota reached{f'; resets in ~{wait/60:.0f} min' if wait else ''}. Re-run to resume.")
                    return EXIT_QUOTA
                pause = max((wait or 0) + 30, DAILY_QUOTA_MIN_SLEEP_S)
                log(f"Daily quota reached; sleeping {pause/3600:.1f} h, then resuming.")
                sleep(pause)
            else:
                sleep(INFRA_RETRY_SLEEP_S)
    return EXIT_DONE


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, choices=sorted(CONFIGS))
    ap.add_argument("--tasks", required=True, type=Path)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--limit", type=int, help="only the first N tasks of the file")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--wait-on-quota", action="store_true")
    ap.add_argument("--model", help="override the config's model (results go to <config>@<model>.jsonl)")
    ap.add_argument("--retry-outcomes", nargs="*", default=[], help="re-run tasks whose final outcome is one of these")
    args = ap.parse_args()
    tasks_file = args.tasks if args.tasks.is_absolute() else Path.cwd() / args.tasks
    config = CONFIGS[args.config]
    name = config.name
    if args.model:  # e.g. develop on gpt-oss-20b's separate quota while gpt-oss-120b runs the baseline
        config = replace(config, model_id=args.model)
        name = f"{config.name}@{args.model.split('/')[-1]}"
    out = args.out or results_path(tasks_file, name)
    return run(config, tasks_file, out, args.repeats, args.limit, args.wait_on_quota, frozenset(args.retry_outcomes))


if __name__ == "__main__":
    sys.exit(main())
