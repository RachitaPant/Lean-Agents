"""Tests for eval/analyze.py on synthetic records."""

import json

from eval.analyze import bootstrap_ci, load_final, summarise, to_markdown


def rec(task, success, repeat=0, final=True, outcome=None, tokens=1000, calls=4, invalid=0):
    return {
        "id": task, "repeat": repeat, "final": final, "success": success,
        "outcome": outcome or ("pass" if success else "checker_fail"),
        "prompt_tokens": tokens, "completion_tokens": 0, "llm_calls": calls,
        "latency_s": 10.0, "invalid_tool_calls": invalid,
    }


def test_load_final_keeps_last_final_per_task_repeat(tmp_path):
    p = tmp_path / "r.jsonl"
    rows = [rec("a", False, final=False, outcome="rate_limited_daily"), rec("a", False), rec("a", True), rec("b", True)]
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = {r["id"]: r for r in load_final(p)}
    assert set(out) == {"a", "b"} and out["a"]["success"] is True


def test_bootstrap_ci_bounds():
    lo, hi = bootstrap_ci([1.0] * 5 + [0.0] * 5)
    assert 0.1 <= lo < 0.5 < hi <= 0.9
    assert bootstrap_ci([1.0] * 4) == (1.0, 1.0)


def test_summary_weighs_tasks_equally_with_repeats():
    records = [rec("a", True, 0), rec("a", False, 1), rec("b", True, 0), rec("b", True, 1)]
    s = summarise(records)
    assert s["tasks"] == 2 and s["success_rate"] == 0.75
    assert s["repeat_agreement"] == {"tasks": 2, "agree": 1, "rate": 0.5}


def test_infra_failures_and_markdown():
    records = [rec("a", True), rec("b", False, outcome="provider_unavailable", invalid=2)]
    s = summarise(records)
    assert s["infra_failures"] == 1 and s["invalid_calls_total"] == 2
    md = to_markdown({"baseline": s})
    assert "| baseline | 2 | 50.0% |" in md and "provider_unavailable: 1" in md


def test_repairs_summarised():
    a = rec("a", True)
    a["repairs"] = [{"category": "wrong_tool", "tool": "answer", "source": "provider"}]
    b = rec("b", False)
    b["repairs"] = [{"category": "wrong_argument", "tool": "x", "source": "client"}] * 2
    s = summarise([a, b, rec("c", True)])
    assert s["repairs"] == {"wrong_argument": 2, "wrong_tool": 1}
    assert (s["tasks_repaired"], s["tasks_repaired_passed"]) == (2, 1)
    assert "2 tasks needed a repair, 1 of them still passed" in to_markdown({"c1_c2": s})
