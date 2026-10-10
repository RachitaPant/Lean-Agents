"""Load the per-API core tools that C1 always offers (built by eval/build_core_tools.py)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CORE_TOOLS_PATH = Path(__file__).with_name("core_tools.json")


@lru_cache(maxsize=1)
def _load() -> dict[str, list[str]]:
    if not CORE_TOOLS_PATH.exists():
        return {}
    return json.loads(CORE_TOOLS_PATH.read_text(encoding="utf-8"))["classes"]


def core_tools_for(classes: list[str]) -> set[str]:
    data = _load()
    return {name for c in classes for name in data.get(c, [])}
