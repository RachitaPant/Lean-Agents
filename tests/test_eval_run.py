"""Offline tests of eval/run.py: resume, quota handling, infra retries. Scripted model, no network."""

import json

from eval.configs import Config
from eval.run import EXIT_DONE, EXIT_QUOTA, load_records, parse_retry_after_s, run
from tests.test_runner import ScriptedModel, text_msg, tool_msg

CFG = Config(name="test", description="scripted")
TPD_ERR = RuntimeError(
    "Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization "
    "`org_x` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 199000, Requested 5000. "
    "Please try again in 7m32.5s.'}}"
)
UNAVAILABLE_ERR = RuntimeError("Error code: 503 - over capacity")


def passing_script():  # multi_turn_base_100
    return [
        tool_msg("get_stock_info", {"symbol": "NVDA"}),
        text_msg("ok"),
        tool_msg("fund_account", {"amount": 2203.4}),
        text_msg("ok"),
    ]


def tasks_file(tmp_path, ids):
    p = tmp_path / "tasks.jsonl"
    p.write_text("".join(json.dumps({"id": i}) + "\n" for i in ids))
    return p


def factory(scripts):
    """Each model construction (one per attempt) consumes the next script."""
    scripts = list(scripts)
    return lambda: ScriptedModel(scripts.pop(0))


def test_parse_retry_after():
    assert parse_retry_after_s("Please try again in 7m32.5s.") == 452.5
    assert parse_retry_after_s("try again in 1h2m3s") == 3723
    assert parse_retry_after_s("try again in 850ms") == 0.85
    assert parse_retry_after_s("no hint") is None


def test_pass_writes_final_record_and_resume_skips(tmp_path):
    out = tmp_path / "out.jsonl"
    tf = tasks_file(tmp_path, ["multi_turn_base_100"])
    assert run(CFG, tf, out, model_factory=factory([passing_script()]), log=lambda *a: None) == EXIT_DONE
    recs = load_records(out)
    assert len(recs) == 1 and recs[0]["final"] and recs[0]["outcome"] == "pass"
    assert recs[0]["config_detail"]["temperature"] == 0.001 and recs[0]["invalid_tool_calls"] == 0
    # second run: nothing to do, no model constructed
    assert run(CFG, tf, out, model_factory=factory([]), log=lambda *a: None) == EXIT_DONE
    assert len(load_records(out)) == 1


def test_daily_quota_stops_without_final_record_then_resumes(tmp_path):
    out = tmp_path / "out.jsonl"
    tf = tasks_file(tmp_path, ["multi_turn_base_100"])
    script = [tool_msg("get_stock_info", {"symbol": "NVDA"}), TPD_ERR]
    assert run(CFG, tf, out, model_factory=factory([script]), log=lambda *a: None) == EXIT_QUOTA
    recs = load_records(out)
    assert len(recs) == 1 and not recs[0]["final"] and recs[0]["outcome"] == "rate_limited_daily"
    # next day: resumes the same task
    assert run(CFG, tf, out, model_factory=factory([passing_script()]), log=lambda *a: None) == EXIT_DONE
    recs = load_records(out)
    assert [r["final"] for r in recs] == [False, True] and recs[-1]["outcome"] == "pass"


def test_wait_on_quota_sleeps_then_continues(tmp_path):
    out = tmp_path / "out.jsonl"
    tf = tasks_file(tmp_path, ["multi_turn_base_100"])
    slept = []
    code = run(
        CFG, tf, out, wait_on_quota=True, sleep=slept.append, log=lambda *a: None,
        model_factory=factory([[TPD_ERR], passing_script()]),
    )
    assert code == EXIT_DONE and slept == [6 * 3600]  # rolling window: wait for a task's worth
    assert load_records(out)[-1]["outcome"] == "pass"


def test_provider_unavailable_retried_then_final(tmp_path):
    out = tmp_path / "out.jsonl"
    tf = tasks_file(tmp_path, ["multi_turn_base_100"])
    run(CFG, tf, out, sleep=lambda s: None, log=lambda *a: None,
        model_factory=factory([[UNAVAILABLE_ERR]] * 3))
    recs = load_records(out)
    assert [r["final"] for r in recs] == [False, False, True]
    assert recs[-1]["outcome"] == "provider_unavailable"


def test_repeats_are_separate_records(tmp_path):
    out = tmp_path / "out.jsonl"
    tf = tasks_file(tmp_path, ["multi_turn_base_100"])
    run(CFG, tf, out, repeats=2, log=lambda *a: None, model_factory=factory([passing_script(), passing_script()]))
    assert sorted(r["repeat"] for r in load_records(out)) == [0, 1]


def test_invalid_calls_counted(tmp_path):
    out = tmp_path / "out.jsonl"
    tf = tasks_file(tmp_path, ["multi_turn_base_100"])
    script = [
        tool_msg("get_stock_info", {"wrong_arg": "NVDA"}),  # rejected by smolagents validation
        tool_msg("get_stock_info", {"symbol": "NVDA"}),
        text_msg("ok"),
        tool_msg("fund_account", {"amount": 2203.4}),
        text_msg("ok"),
    ]
    run(CFG, tf, out, log=lambda *a: None, model_factory=factory([script]))
    rec = load_records(out)[0]
    assert rec["invalid_tool_calls"] == 1 and rec["step_errors"][0]["type"] == "AgentToolCallError"


def test_retry_outcomes_reruns_old_final_records(tmp_path):
    out = tmp_path / "out.jsonl"
    tf = tasks_file(tmp_path, ["multi_turn_base_100"])
    out.write_text(json.dumps({"id": "multi_turn_base_100", "repeat": 0, "final": True, "outcome": "error"}) + "\n")
    run(CFG, tf, out, log=lambda *a: None, model_factory=factory([]))  # nothing to do by default
    assert len(load_records(out)) == 1
    run(CFG, tf, out, retry_outcomes=frozenset({"error"}), log=lambda *a: None, model_factory=factory([passing_script()]))
    assert load_records(out)[-1]["outcome"] == "pass"
