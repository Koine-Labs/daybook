"""Daybook HTTP bridge — FastAPI app.

Run from `apps/` with the inference venv active:
    cd apps && source inference/.venv/bin/activate
    cd api && uvicorn app:app --reload --port 8000

Or from anywhere:
    uvicorn api.app:app --reload --port 8000 \
        --app-dir "/path/to/daybook/apps"
"""
from __future__ import annotations

import sys
from pathlib import Path

# Path bootstrap MUST run before route imports.
# - apps/ on path → enables `from api.routes...` (this file's package)
#   and `from chat...`, `from recall...`, `from wisp...`
# - apps/inference/ on path → enables `from db import get_conn`,
#   `from embeddings import ...`, `from llm import ChatClient`
_HERE = Path(__file__).resolve().parent
_APPS_DIR = _HERE.parent
_INFERENCE_DIR = _APPS_DIR / "inference"
for _p in (_APPS_DIR, _INFERENCE_DIR):
    sp = str(_p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

# Use absolute imports so this works whether uvicorn loads us as `app:app`
# (from apps/api/ as cwd) or as `api.app:app` (from apps/ as cwd).
from api.routes import chat as chat_routes  # noqa: E402
from api.routes import compose as compose_routes  # noqa: E402
from api.routes import health as health_routes  # noqa: E402
from api.routes import observations as observations_routes  # noqa: E402
from api.routes import persona as persona_routes  # noqa: E402
from api.routes import recall as recall_routes  # noqa: E402
from api.routes import sessions as sessions_routes  # noqa: E402


app = FastAPI(
    title="Daybook API",
    description="HTTP bridge exposing Daybook's Python brain to native clients (iOS, web).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_routes.router)
app.include_router(chat_routes.router)
app.include_router(recall_routes.router)
app.include_router(sessions_routes.router)
app.include_router(observations_routes.router)
app.include_router(persona_routes.router)
app.include_router(compose_routes.router)


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    return {
        "name": "Daybook API",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
    }
