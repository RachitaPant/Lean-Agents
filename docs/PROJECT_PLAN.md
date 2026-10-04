# Lean Agents: Phase-Wise Project Plan

**Assumptions:**
- ~10–12 hours/week alongside college.
- Start mid-October 2026; finish by March 2027.
- A 2-week exam buffer is included; move it to match your exam calendar.

**Principles:**
1. **Deploy early.** The live link exists from Week 4, and every improvement ships to it.
2. **C1 first.** Token reduction stretches the free daily quota, which speeds up every later experiment.
3. **Freeze the evaluation task sample after Phase 3.** Never tune on it.
4. **Never write a number in docs or the resume that wasn't measured.**

Progress tracking: tick boxes as you go.

---

## Phase 0: Setup (Week 1)

- [ ] Create accounts (no card needed): GitHub, Vercel, Groq, Google AI Studio (Gemini key), Upstash. GitHub Models works with the GitHub account. **Not Cerebras:** it now requires a card.
- [x] Python 3.12 venv (avoid 3.13 for ML libs) + Node.js LTS (using 3.11.0 in `.venv`, since 3.12 isn't installed; Node 22.15)
- [x] Repo skeleton: `agent/`, `api/`, `web/`, `eval/`, `docs/` (done)
- [x] `requirements.txt`, `.env` from `.env.example`
- [x] Set `OLLAMA_MODELS=D:\ollama` and `HF_HOME=D:\hf` (C: has little free space)
- [ ] GitHub Actions workflow running `pytest`
- [x] `scripts/hello_groq.py`: one chat completion + one tool call against Groq (verified 2026-10-04 with `openai/gpt-oss-120b`)

**Exit:** Groq call works from Python; CI is green.

## Phase 1: Understand the foundations (Weeks 2–3)

- [ ] Read smolagents `src/smolagents/agents.py` (<1,000 LOC), `ToolCallingAgent`, the tools module, the model wrappers
- [ ] Write `docs/ARCHITECTURE_NOTES.md`: how the smolagents loop works and where the hooks for C1–C5 go
- [ ] Read BFCL: the multi-turn data format, `bfcl_eval/eval_checker/multi_turn_eval/func_source_code/*.py`, and how state-based checking works
- [ ] Build `eval/bfcl_adapter.py`: wrap BFCL simulated API methods as smolagents tools (file system, trading bot, messaging first)
- [ ] Run 3 BFCL multi-turn tasks end to end with the stock agent; score them with BFCL's checker

**Exit:** a stock agent solves a BFCL task and the official checker scores it.

## Phase 2: Walking skeleton deployed (Week 4)

- [ ] `api/run.py`: Vercel Python function that runs one task and streams each step (tool, args, result, tokens)
- [ ] `web/`: Next.js page with a preset-task picker and a live step-by-step trace viewer
- [ ] Upstash Redis: per-visitor rate limit + global daily token budget
- [ ] Deploy to Vercel; add the Groq key as an env var in the Vercel dashboard (never commit keys)

**Exit:** a public URL where anyone can click "Run" and watch the agent. Add it to GitHub and LinkedIn.

## Phase 3: Baseline + evaluation harness (Weeks 5–6)

- [ ] `eval/run.py --config <name> --tasks <file>`. Per task it logs:
  - success
  - prompt/completion tokens
  - LLM calls
  - latency
  - invalid tool calls
  - provider used
- [ ] Quota-aware and resumable: pause at the daily limit, resume the next day (append-only JSONL)
- [ ] **Pilot on 10 tasks** → measure real tokens per task → choose the sample size (target 40–60) and fix the seed
- [ ] Freeze `eval/tasks/frozen_sample.jsonl`
- [ ] Run **Baseline** on the frozen sample
- [ ] `eval/analyze.py`: success rate with 95% bootstrap CI, token/latency distributions, tables + plots

**Exit:** a publishable baseline table.

## ⏸ Exam buffer (2 weeks)

- [ ] Light work: read the papers in `RESEARCH_NOTES.md`; let overnight eval runs continue

## Phase 4: C1, tool retrieval (Weeks 7–8)

- [ ] Precompute tool descriptions + embeddings at build time (`agent/retrieval/`)
- [ ] Retrievers: BM25, embedding, hybrid; top-k tools per step
- [ ] Safety net: if the agent names an unseen tool, re-retrieve with a larger k
- [ ] Ablation: k ∈ {3, 5, 10} × {BM25, embedding, hybrid}
- [ ] Run **+C1**; compare with the Baseline
- [ ] Ship to the live demo with a "tokens saved" counter

**Metrics:** tokens per step and per task, success, tasks completed per day on a fixed quota.

## Phase 5: C2, validate and repair (Weeks 9–10)

- [ ] Validate every tool call: Pydantic/jsonschema checks on types, required fields, enums
- [ ] Targeted error feedback (e.g. "`amount` must be a number; got 'ten'"), with a capped number of retries
- [ ] Failure taxonomy: malformed JSON / wrong tool / wrong argument / wrong order
- [ ] Run **+C1+C2**

**Metrics:** invalid-call rate, recovered failures, extra calls spent, success.

## Phase 6: C5, quota-aware provider router (Week 11)

- [ ] Track per-model RPM/TPM/RPD/TPD in Redis
- [ ] Route Groq `gpt-oss-120b` → Groq `qwen3.8-27b` → Groq `gpt-oss-20b` → Gemini Flash (AI Studio) → GitHub Models (Groq limits are per model, so each Groq model is its own quota), failing over on 429s and timeouts, with exponential backoff
- [ ] Load test that simulates concurrent demo visitors

**Metrics:** request success rate under load, with vs. without the router.

## Phase 7: C3, plan caching (Weeks 12–14)

- [ ] On success, extract a plan template (steps with values replaced by placeholders) and store it in Redis
- [ ] On a new task, retrieve similar templates and have the LLM adapt them to the specifics, then execute
- [ ] Reuse guard: if validation fails or a step errors, fall back to normal planning
- [ ] Separate cache warm-up tasks from test tasks (no leakage)
- [ ] Run **+C1+C2+C3**; add a "plan reused" badge to the UI

**Metrics:** LLM calls/tokens per task, latency, success retained, cache hit rate.

## Phase 8: C4, multi-agent study (Weeks 15–16)

- [ ] Planner / executor / verifier via smolagents managed agents
- [ ] Compare against the best single-agent config **at equal token budget**
- [ ] Add a single/multi toggle to the demo
- [ ] Report the result honestly, even if it is negative

## Phase 9: Full evaluation (Weeks 17–18)

- [ ] Re-run all configs on the frozen sample
- [ ] Final table with CIs + significance tests (McNemar for success), ablation charts, failure analysis
- [ ] Record 10–15 showcase runs for the demo's replay mode

**Exit:** every resume placeholder is filled with a measured number.

## Phase 10: Polish, docs, resume (Weeks 19–20)

- [ ] Results dashboard page on the live site
- [ ] README: problem, architecture, **Original vs Our Contribution**, results, local setup, attribution
- [ ] Project report/paper, slides, 2-minute demo video
- [ ] Resume bullets + 90-second interview pitch
- [ ] Optional: upstream issue/PR to smolagents (e.g. a validate-and-repair hook)

---

## Timeline summary

| Weeks | Phase | Live demo shows |
|---|---|---|
| 1 | Setup | — |
| 2–3 | Understand smolagents + BFCL | — |
| **4** | **Walking skeleton** | **Baseline agent, live** |
| 5–6 | Baseline + eval harness | same |
| — | Exam buffer | same |
| 7–8 | C1 Tool retrieval | tokens-saved counter |
| 9–10 | C2 Validate & repair | repaired-call markers |
| 11 | C5 Provider router | stays up under load |
| 12–14 | C3 Plan caching | plan-reused badge |
| 15–16 | C4 Multi-agent | single/multi toggle |
| 17–18 | Full evaluation | replay mode |
| 19–20 | Polish + docs | results dashboard |

## Risks

| Risk | Mitigation |
|---|---|
| Daily token quota slows evaluation | Do C1 first; spread runs across models/providers; 40–60-task sample; overnight runs |
| A free tier changes its limits | Router (C5) + replay mode; keep providers swappable via config |
| Vercel Hobby 300 s function limit | Cap agent steps; stream progress; short tasks on fast APIs |
| A contribution doesn't help | Report it honestly; negative results with analysis are still interview gold |
| Busy semester | Phases after 3 are independent; C4 can be dropped without breaking the story |

## Resume template (fill in after Phase 9)

**Lean Agents: Token-Efficient, Reliable Tool-Using AI Agents** · [Live Demo] · [GitHub]
*Python, smolagents, Groq, Next.js, Vercel, Redis*

- Extended Hugging Face smolagents with retrieval-based tool selection, cutting prompt tokens per agent step by [X]% and raising tasks completed per day on a free API quota by [Y]×.
- Built a schema-validation and repair loop that reduced invalid tool calls by [X]% and raised BFCL multi-turn success from [A]% to [B]%.
- Implemented plan caching and a quota-aware multi-provider LLM router, cutting LLM calls per task by [X]% at [Y]% request success under rate limits.
- Deployed a live agent-trace demo at ₹0 (Vercel, Upstash) with sandboxed tools, per-visitor rate limits and a replay fallback.
