"""PKCE OAuth flow against auth.openai.com — mirrors Codex CLI."""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
REDIRECT_URI = "http://localhost:1455/auth/callback"
SCOPE = "openid profile email offline_access"


@dataclass
class PkcePair:
    verifier: str
    challenge: str


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str
    id_token: str | None
    expires_at: float  # epoch seconds


def generate_pkce() -> PkcePair:
    verifier_bytes = secrets.token_bytes(32)
    verifier = _base64url_encode(verifier_bytes)
    challenge_bytes = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = _base64url_encode(challenge_bytes)
    return PkcePair(verifier=verifier, challenge=challenge)


def generate_state() -> str:
    return secrets.token_hex(16)


def build_authorize_url(*, challenge: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": "codex_cli_rs",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_authorization_code(*, code: str, verifier: str) -> TokenSet:
    body = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": REDIRECT_URI,
    }
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if res.status_code != 200:
        raise RuntimeError(f"Token exchange failed: {res.status_code} {res.text[:300]}")
    return _assert_token_set(res.json())


def refresh_access_token(refresh_token: str) -> TokenSet:
    body = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
    }
    with httpx.Client(timeout=30.0) as client:
        res = client.post(
            TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if res.status_code != 200:
        raise RuntimeError(f"Token refresh failed: {res.status_code} {res.text[:300]}")
    return _assert_token_set(res.json())


def _assert_token_set(payload: dict) -> TokenSet:
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    if not access or not refresh or not isinstance(expires_in, int):
        raise RuntimeError("Token response missing required fields")
    return TokenSet(
        access_token=access,
        refresh_token=refresh,
        id_token=payload.get("id_token"),
        expires_at=time.time() + float(expires_in),
    )


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
