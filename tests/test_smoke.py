"""Phase 0 smoke tests: dependencies import and the repo layout exists. No network."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_core_imports():
    import openai  # noqa: F401
    import smolagents

    assert smolagents.__version__


def test_repo_layout():
    for d in ["agent", "api", "web", "eval", "docs"]:
        assert (ROOT / d).is_dir(), f"missing {d}/"


def test_env_example_has_no_secrets():
    for line in (ROOT / ".env.example").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, value = line.split("=", 1)
        if name.endswith(("_KEY", "_TOKEN")):
            assert value.strip() == "", f"secret value in .env.example: {name}"
