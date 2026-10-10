"""FastAPI backend for the live demo (Vercel Python service; routes under /api).

    GET  /api/health    liveness + which protections are active
    GET  /api/presets   the demo tasks a visitor can pick
    POST /api/run       {"task_id": ..., "agent": "c1"|"baseline"} → NDJSON stream of agent trace events (agent/runner.py)

Only preset tasks can be run, so visitors can't spend the quota on arbitrary inputs.
Local dev: uvicorn server.app:app --port 8000 (the Next.js dev server proxies /api to it).
"""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from typing import Literal

from agent.bfcl_adapter import load_tasks
from agent.lean_agent import LeanOptions
from agent.runner import make_model, stream_task
from server.guard import guard_from_env

load_dotenv()

# Short tasks across domains with few tools, so a run fits Groq's free 8K tokens/minute and
# Vercel's 300 s limit. These are excluded from the frozen evaluation sample.
PRESETS = {
    "multi_turn_base_100": ("Check a stock, then fund the account", "Trading"),
    "multi_turn_base_132": ("Research a stock and review an order", "Trading"),
    "multi_turn_base_50": ("Unlock the car and turn on headlights", "Vehicle"),
    "multi_turn_base_182": ("Price a flight and set a travel budget", "Travel"),
}
DEMO_MAX_STEPS_PER_TURN = 8  # well under BFCL's 20, to bound tokens and time per visitor
DEMO_DEADLINE_S = 200  # stop starting new steps after this; Vercel kills the function at 300 s

TASKS = {t["id"]: t for t in load_tasks(list(PRESETS))}
GUARD = guard_from_env()

app = FastAPI(title="Lean Agents demo API", docs_url=None, redoc_url=None)


AGENTS = {"baseline": None, "c1": LeanOptions()}  # stock smolagents vs C1 (tool retrieval + token budget)


class RunRequest(BaseModel):
    task_id: str
    agent: Literal["baseline", "c1"] = "c1"


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or request.headers.get("x-real-ip", "") or (request.client.host if request.client else "unknown")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "groq_key": bool(os.getenv("GROQ_API_KEY")),
        "guard": "missing" if GUARD is None else type(GUARD.store).__name__,
        "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    }


@app.get("/api/presets")
def presets():
    out = []
    for task_id, (title, domain) in PRESETS.items():
        task = TASKS[task_id]
        out.append(
            {
                "id": task_id,
                "title": title,
                "domain": domain,
                "apis": task["involved_classes"],
                "turns": [" ".join(m["content"] for m in turn) for turn in task["question"]],
            }
        )
    return {"presets": out, "tokens_used_today": GUARD.tokens_used_today() if GUARD else None}


@app.post("/api/run")
def run(body: RunRequest, request: Request):
    if body.task_id not in TASKS:
        return JSONResponse({"error": "Unknown preset."}, status_code=400)
    if GUARD is None:
        return JSONResponse({"error": "Demo protection is not configured (Upstash). Runs are disabled."}, status_code=503)
    if not os.getenv("GROQ_API_KEY"):
        return JSONResponse({"error": "GROQ_API_KEY is not configured."}, status_code=503)

    decision = GUARD.admit(client_ip(request))
    if not decision.ok:
        return JSONResponse(
            {"error": decision.reason},
            status_code=decision.status,
            headers={"Retry-After": str(decision.retry_after_s)},
        )

    def events():
        charged = 0
        try:
            model = make_model()
            for event in stream_task(
                TASKS[body.task_id],
                model,
                max_steps_per_turn=DEMO_MAX_STEPS_PER_TURN,
                deadline_s=DEMO_DEADLINE_S,
                lean=AGENTS[body.agent],
            ):
                if event["type"] == "step":
                    tokens = event["prompt_tokens"] + event["completion_tokens"]
                    GUARD.charge(tokens)
                    charged += tokens
                elif event["type"] == "done":
                    GUARD.charge(event["prompt_tokens"] + event["completion_tokens"] - charged)
                yield json.dumps(event, default=str) + "\n"
        finally:  # also runs if the visitor disconnects mid-stream
            GUARD.release()

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})
