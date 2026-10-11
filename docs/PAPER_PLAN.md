# Paper Plan

A research paper built on C1 and C2, run alongside the project plan. Written 2026-10-12.

**Working title:** *Making tool-using agents work on free-tier LLM APIs: token budgets and repair*

**Core claim:** under free-tier limits (8K tokens/minute, 200K tokens/day), a stock tool-calling
agent fails most BFCL multi-turn tasks for operational reasons (request size, fatal provider
rejections), not task understanding. Prompt-side budgeting (C1) and validate-and-repair (C2)
recover most of that. C3–C4 are optional for the paper; the story stands without them.

**Target venues** (check each call for fit, page limit and deadline before writing):

- Student research workshops at ACL-family conferences (ACL / NAACL / EMNLP / AACL SRW)
- Workshops on LLM agents, tool use or efficient NLP at ICLR, NeurIPS or ACL
- arXiv preprint in any case
- Avoid fee-driven conferences with little review; ask the project guide before choosing one

---

## 1. Evaluation needed for the paper

Pilot numbers so far (10 tasks per config; `eval/results/`) show the effect but are far too
small to publish: baseline 1/10 (95% CI 0–30%), c1 6/10 (30–90%).

| # | Work | Why reviewers need it | Status |
|---|---|---|---|
| P1 | **Noise check:** `c1` twice more on the pilot (`--repeats 3`) | Groq's seed is best-effort; shows how much results move run to run | To do |
| P2 | **Freeze a larger test sample:** 60 tasks from the 154 left after pilot + dev | 10 tasks can't separate configs | To do (after P1) |
| P3 | **Main table on `gpt-oss-120b`:** baseline, c1, c1_c2 on the frozen sample | The headline result | To do |
| P4 | **Second model** (`qwen/qwen3.8-27b`, separate Groq quota): baseline and c1_c2 | Shows the effect isn't one model's quirk | To do |
| P5 | Third model, Gemini via AI Studio, if its free-tier limits allow | Different provider, different limits | Needs the AI Studio key |
| P6 | **Ablations on the dev set** (`gpt-oss-20b`): c1_listing, c1_retrieval, c1, c1_k3, c1_k10, c2, c1_c2 | Attributes savings and success to each lever | c1, c1_c2 running |
| P7 | **Statistics:** paired McNemar on success, bootstrap CIs, tokens per *successful* task | Paired design makes 60 tasks enough for large effects | `analyze.py` has CIs; McNemar to add |
| P8 | **Failure analysis:** taxonomy counts per config, examples of each repair | The paper's qualitative half | Data is being logged |

**Statistical power, stated honestly:** with 60 paired tasks, a jump like the pilot's
(~10% → ~60%) is easy to detect; a C2-on-top-of-C1 gain of 5–10 points probably isn't.
C2 is then argued from secondary metrics (provider rejections recovered, invalid calls per
task, tasks that passed after a repair), not success alone.

## 2. Compute budget (estimates)

Tokens per task, measured in the pilot and dev runs: baseline ~38K, c1 ~16K, c1_c2 ~25–30K.
Each Groq model has its own 200K tokens/day, so models run in parallel.

| Model | Runs | Tokens (est.) | Days at 200K/day |
|---|---|---|---|
| gpt-oss-120b | P1 (20 extra c1 runs) + P3 (3 configs × 60) | ~0.3M + ~4.8M | ~26 |
| qwen3.8-27b | P4 (2 configs × 60) | ~4.1M | ~21 |
| gpt-oss-20b | P6 (7 configs × 10–30 dev tasks) | ~2–5M | ~10–25 |

These are estimates from pilot means, to be replaced by measured totals. Running all three
in parallel overnight finishes in about 4 weeks. **Runs must survive laptop restarts**
(three died so far); a scheduled restart of `eval/run.py` (it resumes safely) would help.

## 3. Related work to read and position against

Titles from memory or `RESEARCH_NOTES.md`. **Open and verify every one (authors, venue,
year, arXiv id) before citing**; don't cite anything not actually read.

| Area | Works to read | What to say about them |
|---|---|---|
| Tool use by LLMs | ReAct (Yao et al.); Toolformer (Schick et al.); Gorilla (Patil et al.); ToolLLM / ToolBench (Qin et al.) | The agent paradigm and tool-use datasets this builds on |
| Benchmark | BFCL and its multi-turn category (Patil et al., Berkeley) | Our evaluation; we reuse its state-based checker unchanged |
| Tool retrieval / selection | ToolLLM's API retriever; other "select relevant tools per query" work (search) | How C1 differs: per-step BM25 + learned core-tool prior + response-field indexing, under a per-request budget |
| Prompt / context compression | LLMLingua (Jiang et al.) and similar | C1 removes redundant tool text structurally instead of compressing prose |
| Self-correction | Reflexion (Shinn et al.); Self-Refine (Madaan et al.); "Structured Reflection for Reliable Tool Interactions" (RESEARCH_NOTES) | C2 uses deterministic, schema-derived feedback and side-effect awareness, not LLM self-critique |
| Reliability of tool agents | "Invocation-Level Reliability of Tool-Using Agents"; "Callability Is Not Operability" (RESEARCH_NOTES) | Our taxonomy from real provider rejections |
| Evaluation methodology | "The Double Measurement Confound in Agent Benchmarks" (RESEARCH_NOTES) | Read before writing the evaluation section |
| Plan caching (if C3 is included) | Agentic Plan Caching (NeurIPS 2025, RESEARCH_NOTES) | Only if C3 makes it into the paper |

The novelty claim must come out of this reading, not before it. Working hypothesis: no prior
work measures tool-agent failure modes under strict free-tier quotas and fixes them with
ablated, provider-agnostic levers on BFCL multi-turn.

## 4. Outline (maps to the project's phases)

1. **Introduction:** free tiers as a real deployment setting; stock agents fail there; contributions.
2. **Setting:** Groq free-tier limits; BFCL multi-turn; smolagents; the turn protocol (Phase 1).
3. **Where the tokens and failures go:** prompt anatomy (90% tool text), outcome categories,
   the per-request ceiling, provider rejections (Phases 1–3 findings).
4. **Method:** C1 levers (Phase 4) and C2 repair with side-effect awareness (Phase 5).
5. **Experimental setup:** task sets and hygiene, configs, models, statistics (Phase 3 harness).
6. **Results:** main table (P3, P4), ablations (P6), noise (P1), tokens per success.
7. **Failure analysis:** taxonomy, repairs that worked and didn't (P8).
8. **Limitations:** 60 tasks, free-tier models only, BFCL base category only, quota-paced runs.
9. **Conclusion.** Appendix: prompts, configs, the adapter fidelity test, reproducibility.

Everything needed for reproducibility is already in the repo: configs in every result
record, git commit per record, seeded task samples, append-only results.

## 5. Timeline

| When | Paper work |
|---|---|
| Oct (now) | P1 noise check, P2 freeze, start P3/P4 overnight; P6 on the dev set |
| Nov (exam buffer) | Runs continue; read section 3's papers (matches the plan's exam-buffer reading) |
| Dec | P7 statistics, P8 failure analysis; draft sections 2–5 |
| Jan | Results and discussion; full draft; guide's review |
| Feb–Mar 2027 | Submit to the chosen venue's deadline; post on arXiv |

## 6. Rules carried over

- Numbers only from `eval/results/` (CLAUDE.md "never invent results").
- No tuning on the frozen sample; all tuning on `dev.jsonl`.
- Report negative or null results (e.g. if C2 adds nothing to success) with analysis.
