"""Session-level auth helpers: get a valid access token, refresh on demand."""
from __future__ import annotations

import time
from dataclasses import dataclass

from .jwt import ChatGptIdentity, decode_identity_from_id_token
from .oauth import TokenSet, refresh_access_token
from .storage import PersistedAuth, clear_auth, read_auth, write_auth


REFRESH_SKEW_SECONDS = 60.0


@dataclass
class ValidAccessToken:
    access_token: str
    identity: ChatGptIdentity


@dataclass
class SignInStatus:
    signed_in: bool
    identity: ChatGptIdentity | None = None


def get_valid_access_token() -> ValidAccessToken:
    persisted = read_auth()
    if persisted is None:
        raise RuntimeError(
            "Not signed in. Run `python -m inference.llm.auth.sign_in`."
        )

    if persisted.tokens.expires_at - REFRESH_SKEW_SECONDS > time.time():
        return ValidAccessToken(
            access_token=persisted.tokens.access_token,
            identity=persisted.identity,
        )

    refreshed = refresh_access_token(persisted.tokens.refresh_token)
    identity = _identity_from_tokens(refreshed, fallback=persisted.identity)
    updated = PersistedAuth(
        tokens=refreshed,
        identity=identity,
        signed_in_at=persisted.signed_in_at,
    )
    write_auth(updated)
    return ValidAccessToken(access_token=refreshed.access_token, identity=identity)


def get_sign_in_status() -> SignInStatus:
    persisted = read_auth()
    if persisted is None:
        return SignInStatus(signed_in=False)
    return SignInStatus(signed_in=True, identity=persisted.identity)


def sign_out() -> None:
    clear_auth()


def _identity_from_tokens(tokens: TokenSet, *, fallback: ChatGptIdentity) -> ChatGptIdentity:
    if tokens.id_token:
        try:
            return decode_identity_from_id_token(tokens.id_token)
        except ValueError:
            pass
    return fallback
