# web/: Lean Agents demo frontend

Next.js page with a preset-task picker and a live, step-by-step trace viewer. It streams
NDJSON events from the Python API (`POST /api/run`, see `../server/app.py`).

Local dev (two terminals, from the repo root):

```bash
.venv/Scripts/python -m uvicorn server.app:app --port 8000
```

```bash
npm --prefix web run dev
```

Then open http://localhost:3000. In dev, `/api/*` is proxied to port 8000 (`next.config.ts`).
