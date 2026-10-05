# Lean Agents

**Reliable, token-efficient tool-using AI agents on free-tier LLMs.**

> Status: 🚧 Phase 2 (walking skeleton). See [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) and the [phase log](docs/PHASE_LOG.md).
>
> Live demo: _coming in Phase 2_ · Results: _coming in Phase 9_

---

## The problem

LLM agents solve tasks by calling tools step by step. In practice they are:

1. **Token-wasteful.** Every step resends the description of *every* available tool. On free API tiers (for example Groq: ~200K tokens/day per model), a naive agent runs out of quota after a few dozen tasks. On paid APIs, the same waste costs money.
2. **Unreliable.** Tool calls arrive with malformed JSON, wrong argument types or the wrong tool, and the task fails.
3. **Repetitive.** Agents re-plan from scratch for tasks that are near-duplicates of ones they already solved.
4. **Fragile.** A single provider's rate limit or outage takes the whole agent down.

**Goal:** complete the same tasks with fewer tokens, fewer failed calls and less repeated planning, survive provider limits, and **prove every improvement with numbers** on a standard benchmark.

## What already exists vs. what this project adds

| Existing open source (foundation) | This project's contribution |
|---|---|
| [smolagents](https://github.com/huggingface/smolagents) (Hugging Face, Apache-2.0): agent loop, tool-calling agents, managed (multi-)agents | **C1: Tool retrieval.** Show the LLM only the top-k relevant tools each step (BM25 / embedding / hybrid) |
| [BFCL](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard) (UC Berkeley, Apache-2.0): multi-turn benchmark with simulated, stateful Python APIs and state-based scoring | **C2: Validate-and-repair.** Check every tool call against its schema and give targeted error feedback for a bounded retry |
| Groq / Gemini / GitHub Models free-tier LLM APIs | **C3: Plan caching.** Reuse plan templates across similar tasks (inspired by [Agentic Plan Caching, NeurIPS 2025](https://arxiv.org/abs/2506.14852)) |
| | **C4: Multi-agent study.** Planner / executor / verifier vs. single agent at an equal token budget |
| | **C5: Quota-aware provider router.** Tracks per-model RPM/TPM/TPD and fails over (Groq models → Gemini → GitHub Models) |
| | Evaluation harness, live streaming demo, results dashboard |

## Architecture

```
                 Visitor opens link (one click)
                              │
        ┌─────────────────────▼──────────────────────┐
        │  Next.js frontend  (Vercel Hobby)          │
        │  • pick a task  • watch agent steps live   │
        │  • baseline vs improved, side by side      │
        │  • evaluation results dashboard            │
        └─────────────────────┬──────────────────────┘
                              │ streamed steps
        ┌─────────────────────▼──────────────────────┐
        │  Python function /api/run  (Vercel)        │
        │  smolagents agent loop, extended with:     │
        │   C1 Tool retrieval → only top-k tools     │
        │   C2 Validator + repair on every call      │
        │   C3 Plan cache lookup / store             │
        │   C4 Planner / Executor / Verifier agents  │
        │   C5 Provider router (quota-aware)         │
        │  Tools = BFCL simulated APIs (sandboxed)   │
        └───────┬────────────────────────┬───────────┘
                │                        │
   ┌────────────▼──────────┐   ┌─────────▼──────────────────┐
   │ Upstash Redis (free)  │   │ LLM APIs (free tiers)      │
   │ • plan cache          │   │ Groq gpt-oss-120b / qwen   │
   │ • rate limit / budget │   │ → Gemini → GitHub Models   │
   │ • recorded replays    │   └────────────────────────────┘
   └───────────────────────┘
```

Public-demo safety:
- **Sandboxed tools.** The tools are BFCL's in-memory simulated APIs, so nothing real is touched.
- **Quota protection.** Per-visitor rate limits plus a daily token budget.
- **Replay fallback.** When the budget is spent, the site replays recorded runs.

## Tools the agent uses (BFCL simulated APIs)

| API | Source file | Examples |
|---|---|---|
| File system | `gorilla_file_system.py` | navigate, create, move, read, search files |
| Trading bot | `trading_bot.py` | stock lookup, place/cancel orders, watchlist |
| Travel booking | `travel_booking.py` | search/book/cancel flights, budget |
| Vehicle control | `vehicle_control.py` | locks, engine, fuel, tires |
| Messaging | `message_api.py` | send/read/delete messages |
| Social posting | `posting_api.py` | post, comment, follow |
| Support tickets | `ticket_api.py` | create/update/resolve tickets |
| Math | `math_api.py` | arithmetic, statistics, conversions |

Skipped: `web_search.py` (requires paid SerpAPI). Memory APIs are a stretch goal.

## Tech stack (all ₹0)

| Layer | Choice |
|---|---|
| Agent framework | smolagents (Apache-2.0) |
| Benchmark + tools | BFCL (Apache-2.0) |
| LLMs | Groq free tier (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`); fallbacks: Gemini Flash via Google AI Studio, then GitHub Models. All without a card. |
| Local LLM | Not used by default (RAM-heavy on the 8 GB dev machine). Ollama + `qwen2.5:3b-instruct` only as a last resort. |
| Retrieval (C1) | `rank-bm25`; `sentence-transformers` (embeddings precomputed at build time) |
| Validation (C2) | Pydantic / jsonschema |
| Cache, rate limit, budget | Upstash Redis (free tier) |
| Backend | Python serverless functions on Vercel (streaming) |
| Frontend | Next.js + TypeScript + Tailwind + Recharts |
| Evaluation | pandas, NumPy/SciPy (bootstrap CIs), matplotlib |
| Testing / CI | pytest, GitHub Actions |

## Evaluation

| Config | Description |
|---|---|
| Baseline | Stock smolagents `ToolCallingAgent` |
| +C1 | Tool retrieval |
| +C1+C2 | + validate-and-repair |
| +C1+C2+C3 | + plan caching |
| C4 | Multi-agent variant at an equal token budget |

**Metrics:**
- task success rate (BFCL state-based checker)
- tokens per task and per step
- LLM calls per task
- latency
- invalid-call rate
- tasks completed per day on a fixed free quota
- router request-success rate under load

**Reporting:**
- a fixed, seeded sample of BFCL multi-turn tasks (size set after the Phase 3 pilot)
- 95% bootstrap confidence intervals
- ablations for each contribution

No results are reported until they are measured.

## Repository layout

```
agent/   Python core: agent extensions (retrieval, validation, plan cache, router, multi-agent)
api/     Vercel Python serverless functions (/api/run, streaming)
web/     Next.js frontend (trace viewer, results dashboard)
eval/    Benchmark harness, BFCL adapter, analysis scripts, results
docs/    Project plan, architecture notes, research notes
```

## Getting started (dev)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt  # created in Phase 0
copy .env.example .env           # then add your API keys
```

## Attribution

This project builds on:
- **smolagents** © Hugging Face, Apache License 2.0
- **Berkeley Function Calling Leaderboard (BFCL)** © Gorilla / UC Berkeley, Apache License 2.0. A subset is vendored unmodified in `third_party/bfcl_eval/` (see its `NOTICE.md`); modified files, if any, are marked.

Ideas reimplemented from papers are cited in [docs/RESEARCH_NOTES.md](docs/RESEARCH_NOTES.md).
