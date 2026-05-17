"""JWT authentication for WebSocket connections."""

from __future__ import annotations

from typing import Optional

import jwt


def validate_token(token: str, secret: str) -> str:
    """Validate a JWT and return the user_id (sub claim)."""
    payload = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["sub", "exp", "iat"]})
    return payload["sub"]


def extract_token_from_header(header: Optional[str]) -> Optional[str]:
    """Extract JWT from 'Bearer <token>' authorization header."""
    if not header or not header.startswith("Bearer "):
        return None
    return header[7:]
