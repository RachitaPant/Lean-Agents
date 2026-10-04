# CLAUDE.md

Context for AI coding sessions on this repo.

## What this is

**Lean Agents** is a B.Tech CSE final-year project (2026–27). It extends Hugging Face **smolagents** with:
- **C1** tool retrieval
- **C2** validate-and-repair
- **C3** plan caching
- **C4** multi-agent study
- **C5** quota-aware provider router

It is evaluated on **BFCL multi-turn** tasks (simulated, sandboxed Python APIs) and deployed at ₹0 on Vercel + Upstash, with Groq free-tier LLMs (fallbacks: Gemini via AI Studio, GitHub Models).

- Plan and progress checkboxes: `docs/PROJECT_PLAN.md`. Check the current phase there first.
- Verified facts, free-tier limits and papers: `docs/RESEARCH_NOTES.md`.

## Hard rules

- **₹0 infrastructure.** Free tiers only, no card-required services. Confirm "no card" on the provider's own signup or limits page; third-party summaries were wrong about Cerebras. No paid APIs (e.g. SerpAPI), so skip BFCL `web_search`.
- **Never commit API keys.** Use `.env` locally and Vercel env vars in deployment.
- **Never invent results.** Resume and README numbers come only from `eval/` outputs.
- **Evaluation hygiene.** Don't tune on `eval/tasks/frozen_sample.jsonl` once it's frozen (Phase 3). Plan-cache warm-up tasks must be disjoint from test tasks.
- **Attribution.** smolagents and BFCL are Apache-2.0. Keep their license notices and mark modified files.
- Keep providers swappable via config. Free-tier limits change.

## Environment

- Windows 11, 8 GB RAM, no CUDA. Use Python 3.12 (not 3.13) for ML libs.
- Ollama with `qwen2.5:3b-instruct` is for local dev only. 7B models are unusable on this machine.
- Store model caches on D: (`OLLAMA_MODELS=D:\ollama`, `HF_HOME=D:\hf`); C: is low on space.

## Layout

```
agent/  core extensions (retrieval/, validation/, plan_cache/, router/, multi_agent/)
api/    Vercel Python functions (/api/run streams agent steps)
web/    Next.js + TS + Tailwind frontend
eval/   BFCL adapter, run.py, analyze.py, tasks/, results/
docs/   plan, research notes, architecture notes
```
