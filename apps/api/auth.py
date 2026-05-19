"""X-API-Key middleware for the public Cloudflare Tunnel.

Loopback requests (localhost / 127.0.0.1) skip the check so local Mac dev
works without a key. Everything else needs the header to match
DAYBOOK_API_KEY from apps/inference/.env.local.

Always-public paths (health, docs, root) bypass the check too — needed for
Cloudflare's edge health pings + OpenAPI docs viewing.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Load .env.local from apps/inference/ (same file db.py uses).
_ENV_PATH = Path(__file__).resolve().parent.parent / "inference" / ".env.local"
load_dotenv(_ENV_PATH)

_EXPECTED_KEY = os.environ.get("DAYBOOK_API_KEY")
_HEADER = "X-API-Key"

# Paths that bypass auth — Cloudflare edge health checks + browsable docs.
_PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}

# Loopback hosts considered "local" — auth not enforced from them, UNLESS
# the request came through Cloudflare (see _is_through_cloudflare below).
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

# CF-specific headers — set by Cloudflare's edge on every proxied request.
# If any is present, the request came through the tunnel, NOT from true
# loopback — so we must enforce auth even though request.client.host
# appears as 127.0.0.1 (cloudflared bridges the connection locally).
_CF_HEADERS = ("cf-connecting-ip", "cf-ray", "cf-visitor")


def _is_through_cloudflare(request: Request) -> bool:
    return any(h in request.headers for h in _CF_HEADERS)


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip public paths
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        # Skip loopback (Mac-local dev) — but only if NOT proxied by CF.
        client_host = request.client.host if request.client else None
        if client_host in _LOCAL_HOSTS and not _is_through_cloudflare(request):
            return await call_next(request)

        # If no key is configured server-side, fail closed and warn.
        if not _EXPECTED_KEY:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": (
                        "DAYBOOK_API_KEY not configured on server. "
                        "Add it to apps/inference/.env.local and restart."
                    ),
                },
            )

        provided = request.headers.get(_HEADER)
        if provided != _EXPECTED_KEY:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid X-API-Key header."},
            )

        return await call_next(request)
