# Licences and credits

## What the MIT licence covers

The [MIT licence](LICENSE) covers only code written for this project. It does not cover anything
listed below, which stays under its own licence and belongs to its own authors.

## Included in this repository

| Work | Authors | Licence | How it is used |
|---|---|---|---|
| [Berkeley Function Calling Leaderboard (BFCL)](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard) | Gorilla / BFCL authors | Apache-2.0 | A subset is vendored unmodified in `third_party/bfcl_eval/`, with its `LICENSE` and `NOTICE.md`: the simulated APIs, checker and multi-turn data. |

**Derived from BFCL data:** `agent/retrieval/core_tools.json` is built from BFCL ground truth, and
`eval/tasks/*.jsonl` list BFCL task IDs.

## Built on

| Work | Authors | Licence | How it is used |
|---|---|---|---|
| [smolagents](https://github.com/huggingface/smolagents) | Hugging Face | Apache-2.0 | The agent loop. `agent/lean_agent.py` subclasses `ToolCallingAgent` and, at runtime, rewrites part of its system prompt template. |

## Python dependencies

Installed separately through `requirements.txt` and `requirements-dev.txt`, not redistributed here.

| Package | Licence | Used for |
|---|---|---|
| [openai](https://github.com/openai/openai-python) | Apache-2.0 | OpenAI-compatible API client |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | BSD-3-Clause | Local configuration |
| [FastAPI](https://github.com/fastapi/fastapi) | MIT | Demo API |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT | Demo API models |
| [jsonschema](https://github.com/python-jsonschema/jsonschema) | MIT | Listed runtime dependency |
| [upstash-redis](https://github.com/upstash/redis-py) | MIT | Rate limits and budget |
| [mpmath](https://github.com/mpmath/mpmath) | BSD-3-Clause | Needed by BFCL's MathAPI |
| [PyYAML](https://github.com/yaml/pyyaml) | MIT | Reading smolagents prompt templates |
| [pytest](https://github.com/pytest-dev/pytest) | MIT | Tests |
| [HTTPX](https://github.com/encode/httpx) | BSD-3-Clause | API tests |
| [Uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause | Local API server |
| [Matplotlib](https://github.com/matplotlib/matplotlib) | Matplotlib licence (PSF-based) | Evaluation plots |

## Web dependencies

Installed through `web/package.json`, not redistributed here. Each also brings its own transitive
dependencies, which aren't listed individually.

| Package | Licence | Used for |
|---|---|---|
| [Next.js](https://github.com/vercel/next.js) (includes `eslint-config-next`) | MIT | Frontend framework |
| [React and React DOM](https://github.com/facebook/react) | MIT | UI |
| [Tailwind CSS](https://github.com/tailwindlabs/tailwindcss) | MIT | Styling |
| [TypeScript](https://github.com/microsoft/TypeScript) | Apache-2.0 | Type checking |
| [ESLint](https://github.com/eslint/eslint) | MIT | Linting |
| [DefinitelyTyped](https://github.com/DefinitelyTyped/DefinitelyTyped) (`@types/*`) | MIT | Type definitions |

## Ideas

- **BM25** ranking (Robertson and colleagues) is reimplemented in `agent/retrieval/bm25.py`, with no
  library code copied.
- **Agentic Plan Caching** ([arXiv:2506.14852](https://arxiv.org/abs/2506.14852)) inspires the planned C3
  contribution, which isn't built yet.
- Other reading is listed in [docs/RESEARCH_NOTES.md](docs/RESEARCH_NOTES.md).

Licence details were read from installed package metadata and project documents on 2026-10-31. Check each
project's own licence before redistributing it. Nothing here implies endorsement by these projects.
