"""Persisted auth tokens at ~/.daybook/auth.json (0600)."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .jwt import ChatGptIdentity
from .oauth import TokenSet


AUTH_DIR = Path.home() / ".daybook"
AUTH_FILE = AUTH_DIR / "auth.json"


@dataclass
class PersistedAuth:
    tokens: TokenSet
    identity: ChatGptIdentity
    signed_in_at: float  # epoch seconds


def read_auth() -> PersistedAuth | None:
    if not AUTH_FILE.exists():
        return None
    try:
        raw = json.loads(AUTH_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    try:
        tokens = TokenSet(**raw["tokens"])
        identity = ChatGptIdentity(**raw["identity"])
        signed_in_at = float(raw["signed_in_at"])
    except (KeyError, TypeError, ValueError):
        return None
    return PersistedAuth(tokens=tokens, identity=identity, signed_in_at=signed_in_at)


def write_auth(auth: PersistedAuth) -> None:
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(AUTH_DIR, 0o700)
    except OSError:
        pass
    payload = {
        "tokens": asdict(auth.tokens),
        "identity": asdict(auth.identity),
        "signed_in_at": auth.signed_in_at,
    }
    # Write atomically with 0600 perms
    tmp = AUTH_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(AUTH_FILE)


def clear_auth() -> None:
    if AUTH_FILE.exists():
        AUTH_FILE.unlink()


def now_epoch() -> float:
    return time.time()
