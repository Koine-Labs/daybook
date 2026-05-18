"""Decode id_token to extract chatgpt_account_id (required header on Codex calls)."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass


@dataclass
class ChatGptIdentity:
    account_id: str
    email: str | None = None
    name: str | None = None


def decode_identity_from_id_token(id_token: str) -> ChatGptIdentity:
    payload = _decode_jwt_payload(id_token)
    if payload is None:
        raise ValueError("Failed to decode id_token")

    auth = payload.get("https://api.openai.com/auth") or {}
    account_id = auth.get("chatgpt_account_id") or auth.get("user_id")
    if not account_id:
        raise ValueError("id_token missing chatgpt_account_id / user_id claim")

    return ChatGptIdentity(
        account_id=str(account_id),
        email=payload.get("email"),
        name=payload.get("name"),
    )


def _decode_jwt_payload(token: str) -> dict | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        encoded = parts[1]
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        return None
