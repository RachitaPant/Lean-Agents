# Phase Log

A running record of each phase: what was done, what we found, and how the project's direction
changed as a result. It is written at the end of each phase (and updated mid-phase when a
finding changes the plan).

- **Plan and checkboxes:** [PROJECT_PLAN.md](PROJECT_PLAN.md)
- **Technical detail:** [ARCHITECTURE_NOTES.md](ARCHITECTURE_NOTES.md)
- **External facts and limits:** [RESEARCH_NOTES.md](RESEARCH_NOTES.md)

Numbers here come only from files in `eval/results/` or from commands run during the phase.

---

## Project flow at a glance

How the direction has moved so far, newest last:

1. **Chose Lean Agents** (2026-10-04): smolagents + BFCL multi-turn, with five contributions
   (C1–C5), ₹0 infrastructure, a live demo from Week 4.
2. **Dropped Cerebras** (Phase 0): it needs a card. The fallback chain became Groq models →
   Gemini (AI Studio) → GitHub Models.
3. **No local models** (Phase 0): Ollama/local embeddings use too much of the 8 GB RAM. Hosted
   free tiers only, unless truly necessary.
4. **Vendored a minimal BFCL** instead of `pip install bfcl-eval` (Phase 1): the package pulls in
   torch and many SDKs, too heavy for the laptop and for Vercel.
5. **Baseline = stock smolagents + BFCL's turn protocol** (Phase 1): pure stock smolagents
   crashes on Groq at step 2 of every task, which measures nothing.
6. **Measure first, fix later** (Phase 1): the failures found are exactly what C1/C2 target, so
   they are scoped to those phases. Only measurement bugs get fixed before the baseline.
7. **C1 widened to "tool retrieval + token budget"** (Phase 1): Groq's 8K tokens-per-request
   ceiling means long tasks can't run at all without trimming.
8. **One agent code path for demo and eval** (Phase 2): `agent/runner.py` streams trace events;
   the FastAPI demo and the eval scripts both consume it, so the demo shows exactly what is
   measured.
9. **One demo run at a time** (Phase 2): 8K tokens/minute can't serve two concurrent runs. A
   global lock keeps the demo usable until the C5 router (Phase 6).

---

## Phase 0: Setup (2026-10-04)

**Goal:** a working Python environment, a Groq call from Python, CI green.

**Done**
- Python **3.11** venv (`.venv`). The plan said 3.12, but only 3.11/3.13 were installed; 3.11
  meets smolagents' ≥3.10. Node 22.15 already present.
- `requirements.txt` pinned to `smolagents[openai]==1.26.0`.
- `OLLAMA_MODELS=D:\ollama`, `HF_HOME=D:\hf` set as user env vars; existing 1.8 GB Ollama models
  copied to D:.
- `scripts/hello_groq.py`: chat completion + full tool-call round trip on `openai/gpt-oss-120b`.
  Worked first time.
- GitHub Actions running `pytest`; green on first push.

**Findings**
- **Cerebras requires a payment card** to activate API access, contrary to third-party
  write-ups. Rejected under the ₹0 / no-card rule; replaced by Gemini (AI Studio) and GitHub
  Models as router fallbacks.
- Running `ollama list` silently starts the Ollama server, which holds RAM.

**Decisions that changed the plan**
- No local models by default (rule in `CLAUDE.md`).
- CI jobs that need API keys (live provider smoke tests) moved to *Future scope*.

---

## Phase 1: Understand the foundations (2026-10-04 → 05)

**Goal:** understand smolagents and BFCL; run a stock agent on BFCL tasks and score them with
the official checker.

**Done**
- Read smolagents' agent loop, tools and model wrappers; read BFCL's multi-turn data, simulated
  APIs, inference loop and checker. Written up in `ARCHITECTURE_NOTES.md`.
- Vendored a minimal, unmodified BFCL v4 subset in `third_party/bfcl_eval/` (8 API classes,
  checker, base data; ~1 MB, Apache-2.0 notice kept).
- `eval/bfcl_adapter.py`: wraps every BFCL method as a smolagents tool, logs each executed call
  as a BFCL call string, and scores with the official checker.
- **Fidelity test:** replaying the ground truth of all 200 base tasks through the adapter scores
  valid on every one (`tests/test_bfcl_adapter.py`, 209 tests in CI).
- `eval/run_smoke.py`: stock agent on 3 dev tasks (`multi_turn_base_3`, `_17`, `_100`).

**Results** (single runs; small samples, not benchmark numbers)

| Config | Model | Passed | File |
|---|---|---|---|
| Pure stock smolagents | gpt-oss-120b | 0/3 | `phase1_smoke_strict_stock.jsonl` |
| Stock + BFCL turn protocol | gpt-oss-120b | 1/3 | `phase1_smoke.jsonl` |
| Stock + BFCL turn protocol, failed tasks re-run | gpt-oss-20b | 0/2 | `phase1_smoke_gpt-oss-20b.jsonl` |

**Findings**
1. **BFCL scores by replaying call strings**, not by inspecting our objects. The adapter must
   log exactly the calls that reached the APIs.
2. **Pure stock smolagents can't run on Groq:** it forces a tool call every step, the model
   replies in text, Groq returns HTTP 400, and smolagents treats that as fatal.
3. **An adapter bug of ours:** optional params were marked with smolagents' non-standard
   `nullable`; Groq ignored it and rejected `null`. Fixed with `type: [T, "null"]`.
4. **One bad provider response kills the whole task.** Three variants were seen: text under
   `tool_choice=required`, an invented `answer` tool, and unparseable output.
5. **Tool descriptions are sent twice per call** (system prompt + native `tools`), and the full
   history is replayed every step.
6. **Tokens per task: 4K to 137K.** One passing task used ~80K, about 40% of a model's daily
   quota. Runs are slow at 8K tokens/minute (one task took 45 min).
7. **HTTP 413:** one request needed 8,113 tokens, more than Groq's 8K per-minute limit. That is
   a hard ceiling: long tasks are impossible without trimming.
8. **Repair hazards:** on a zero-argument tool the model invented `{"arguments": {}}`; after
   each rejection it re-sent a message, so the message went out 4×.
9. **Results vary run to run:** `multi_turn_base_100` passed once and failed once.
10. A smaller model (gpt-oss-20b) didn't avoid any of this; it used the same per-step tokens.

**Decisions that changed the plan**
- Baseline = stock smolagents + BFCL's turn protocol (`tool_choice="auto"`; a text reply ends the
  turn). This mirrors the benchmark and applies to every config.
- Findings 4 and 8 → **C2** items; findings 5 and 7 → **C1**, renamed "tool retrieval + token
  budget" with history trimming.
- **Phase 3** additions: outcome categories (pass / checker_fail / provider_reject /
  request_too_large / step_cap), 429 = resume not fail, a noise check (two baseline runs on ~5
  tasks), sample size set from the measured token budget, dev smoke tasks excluded from the
  frozen sample.

---

## Phase 2: Walking skeleton deployed (in progress, started 2026-10-05)

**Goal:** a public URL where anyone can click "Run" and watch the agent.

**Done so far**
- `agent/runner.py`: the shared agent loop, moved out of `eval/run_smoke.py`. It yields trace
  events (`turn_start`, `tool_call`, `tool_result`, `step`, `turn_end`, `run_error`, `done`) and
  classifies outcomes (pass / checker_fail / provider_reject / request_too_large /
  rate_limited / timeout / step_cap), which is an early part of the Phase 3 categories.
- `server/app.py` (FastAPI): `GET /api/presets`, `POST /api/run` streaming NDJSON. Only 4
  short preset tasks can run (`multi_turn_base_50`, `_100`, `_132`, `_182`; 18–22 tools each).
  Demo caps: 8 steps per turn, 200 s deadline.
- `server/guard.py`: per-visitor hourly limit (hashed IPs), daily token budget, and a single
  run lock, on Upstash (memory store locally). Fails closed on Vercel if Upstash is missing.
- `web/`: Next.js 16 page with preset cards, a live trace (tool calls, results, tokens per
  step) and the BFCL verdict.
- `vercel.json`: Vercel Services, with Next.js at `/` and the Python service at `/api/*`.
- Tests: 223 Python tests (runner with a scripted fake model, guard, API); a CI job for the
  web app (lint, typecheck, build).
- Verified locally: a real run streamed to the browser and was scored by the checker.

**Findings so far**
1. **Vercel Services** (beta, all plans) deploy a Next.js frontend and a Python service as one
   project on one domain, with streaming on by default. Function limits: 300 s, 500 MB.
2. The backend lives in `server/`, not `api/`. On Vercel an `api/` folder triggers the older
   per-file function mode, which could conflict with the FastAPI service.
3. **smolagents at the step cap:** it re-yields the last step and makes one extra "final
   answer" LLM call that it never yields. The runner de-duplicates steps, takes token totals
   from agent memory, and **stops the task at the cap** (BFCL fails it anyway), saving quota.
4. The first live demo run failed with a **fourth provider-rejection variant**: the model
   called a non-existent tool `json`. The baseline demo will often show failures; that is
   the honest "before" picture for C2.
5. `next dev` rewrites proxy `/api` to the local FastAPI server, which mirrors the production
   routing.

- Upstash (free tier, Mumbai) verified: counters, budget and the run lock all work against the real database.

**Waiting on the user:** the Vercel project setup and its environment variables.
