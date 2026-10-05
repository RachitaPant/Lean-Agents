"""Demo protection: per-visitor rate limit, a global daily token budget, and one run at a time.

The free Groq tier allows 8K tokens/minute per model, and one agent step is ~4–7K tokens, so
two concurrent runs would rate-limit each other. A single global run lock keeps the demo usable;
the C5 router (Phase 6) is what lets it scale past one run.

State lives in Upstash Redis (REST) when configured, else in process memory (local dev only).
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

LOCK_KEY = "demo:run_lock"


class MemoryStore:
    """In-process store for local dev. Not shared between processes."""

    def __init__(self):
        self._data: dict[str, tuple[int | str, float | None]] = {}
        self._mu = threading.Lock()

    def _alive(self, key):
        item = self._data.get(key)
        if item and item[1] is not None and item[1] < time.time():
            del self._data[key]
            return None
        return item

    def incrby(self, key: str, n: int, ttl: int) -> int:
        with self._mu:
            item = self._alive(key)
            value = int(item[0]) + n if item else n
            self._data[key] = (value, item[1] if item else time.time() + ttl)
            return value

    def get_int(self, key: str) -> int:
        with self._mu:
            item = self._alive(key)
            return int(item[0]) if item else 0

    def acquire(self, key: str, ttl: int) -> bool:
        with self._mu:
            if self._alive(key):
                return False
            self._data[key] = ("1", time.time() + ttl)
            return True

    def release(self, key: str) -> None:
        with self._mu:
            self._data.pop(key, None)


class UpstashStore:
    def __init__(self, url: str, token: str):
        from upstash_redis import Redis

        self.r = Redis(url=url, token=token, allow_telemetry=False)

    def incrby(self, key: str, n: int, ttl: int) -> int:
        value = self.r.incrby(key, n)
        if value == n:  # first write in this window
            self.r.expire(key, ttl)
        return int(value)

    def get_int(self, key: str) -> int:
        return int(self.r.get(key) or 0)

    def acquire(self, key: str, ttl: int) -> bool:
        return bool(self.r.set(key, "1", nx=True, ex=ttl))

    def release(self, key: str) -> None:
        self.r.delete(key)


@dataclass
class Decision:
    ok: bool
    status: int = 200
    reason: str = ""
    retry_after_s: int = 0


class Guard:
    def __init__(self, store, runs_per_ip_per_hour: int, daily_token_budget: int, lock_ttl_s: int):
        self.store = store
        self.runs_per_ip_per_hour = runs_per_ip_per_hour
        self.daily_token_budget = daily_token_budget
        self.lock_ttl_s = lock_ttl_s

    @staticmethod
    def _day() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _budget_key(self) -> str:
        return f"demo:tokens:{self._day()}"

    def tokens_used_today(self) -> int:
        return self.store.get_int(self._budget_key())

    def admit(self, ip: str) -> Decision:
        """Check budget, take the run lock, then count the visitor's run. Order matters: a
        rejected request must not consume the visitor's hourly allowance."""
        if self.tokens_used_today() >= self.daily_token_budget:
            return Decision(False, 429, "The demo's daily token budget is used up. Try again tomorrow (UTC).", 3600)
        if not self.store.acquire(LOCK_KEY, self.lock_ttl_s):
            return Decision(False, 429, "Another visitor's run is in progress (free tier: one at a time). Try again in a minute.", 60)
        hour = int(time.time() // 3600)
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]  # never store raw IPs
        runs = self.store.incrby(f"demo:ip:{ip_hash}:{hour}", 1, 3600)
        if runs > self.runs_per_ip_per_hour:
            self.release()
            return Decision(False, 429, f"Limit is {self.runs_per_ip_per_hour} runs per hour. Try again later.", 3600 - int(time.time() % 3600))
        return Decision(True)

    def charge(self, tokens: int) -> None:
        if tokens > 0:
            self.store.incrby(self._budget_key(), tokens, 2 * 86400)

    def release(self) -> None:
        self.store.release(LOCK_KEY)


def guard_from_env() -> Guard | None:
    """Upstash in production; memory store locally. None = misconfigured production."""
    url, token = os.getenv("UPSTASH_REDIS_REST_URL"), os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if url and token:
        store = UpstashStore(url, token)
    elif os.getenv("VERCEL"):
        return None  # fail closed: never run unprotected on the public deployment
    else:
        store = MemoryStore()
    return Guard(
        store,
        runs_per_ip_per_hour=int(os.getenv("PER_IP_RUNS_PER_HOUR", "5")),
        daily_token_budget=int(os.getenv("DAILY_TOKEN_BUDGET", "150000")),
        lock_ttl_s=300,
    )
