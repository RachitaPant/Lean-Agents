"""Offline tests of the demo API and its guard. The LLM is replaced by a scripted model."""

import json

import pytest
from fastapi.testclient import TestClient

import server.app as app_module
from server.guard import LOCK_KEY, Guard, MemoryStore
from tests.test_runner import ScriptedModel, text_msg, tool_msg


def make_guard(**kw):
    defaults = dict(runs_per_ip_per_hour=2, daily_token_budget=1000, lock_ttl_s=300)
    return Guard(MemoryStore(), **{**defaults, **kw})


# --- guard -------------------------------------------------------------------------------

def test_one_run_at_a_time():
    g = make_guard()
    assert g.admit("1.1.1.1").ok
    second = g.admit("2.2.2.2")
    assert not second.ok and "in progress" in second.reason
    g.release()
    assert g.admit("2.2.2.2").ok


def test_per_ip_hourly_limit_and_rejections_dont_count():
    g = make_guard(runs_per_ip_per_hour=2)
    for _ in range(2):
        assert g.admit("1.1.1.1").ok
        g.release()
    # a lock rejection must not use up another visitor's allowance
    g.store.acquire(LOCK_KEY, 300)
    assert not g.admit("3.3.3.3").ok
    g.release()
    third = g.admit("1.1.1.1")
    assert not third.ok and "per hour" in third.reason
    assert g.admit("3.3.3.3").ok


def test_daily_budget():
    g = make_guard(daily_token_budget=100)
    g.charge(100)
    d = g.admit("1.1.1.1")
    assert not d.ok and "budget" in d.reason


# --- API ---------------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_module, "GUARD", make_guard(daily_token_budget=10_000))
    monkeypatch.setenv("GROQ_API_KEY", "test")
    return TestClient(app_module.app)


def test_presets(client):
    data = client.get("/api/presets").json()
    ids = [p["id"] for p in data["presets"]]
    assert "multi_turn_base_100" in ids and all(p["turns"] for p in data["presets"])


def test_unknown_preset_rejected(client):
    assert client.post("/api/run", json={"task_id": "multi_turn_base_3"}).status_code == 400


def test_run_streams_events_charges_budget_and_releases_lock(client, monkeypatch):
    script = [
        tool_msg("get_stock_info", {"symbol": "NVDA"}),
        text_msg("NVDA is $220.34"),
        tool_msg("fund_account", {"amount": 2203.4}),
        text_msg("Funded"),
    ]
    monkeypatch.setattr(app_module, "make_model", lambda: ScriptedModel(script))
    resp = client.post("/api/run", json={"task_id": "multi_turn_base_100"})
    assert resp.status_code == 200
    events = [json.loads(line) for line in resp.text.splitlines()]
    assert events[0]["type"] == "run_start" and events[-1]["type"] == "done"
    assert events[-1]["outcome"] == "pass"
    guard = app_module.GUARD
    assert guard.tokens_used_today() == events[-1]["prompt_tokens"] + events[-1]["completion_tokens"]
    assert guard.admit("9.9.9.9").ok  # lock was released after the stream


def test_busy_returns_429(client):
    app_module.GUARD.store.acquire(LOCK_KEY, 300)
    resp = client.post("/api/run", json={"task_id": "multi_turn_base_100"})
    assert resp.status_code == 429 and "Retry-After" in resp.headers


def test_production_without_upstash_fails_closed(monkeypatch):
    from server.guard import guard_from_env

    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    assert guard_from_env() is None
