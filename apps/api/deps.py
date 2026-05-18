"""Shared FastAPI dependencies: default user, DB conn yielder."""
from __future__ import annotations

from api import _paths  # noqa: F401

from db import get_conn as _db_get_conn  # noqa: E402


DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def current_user_id() -> str:
    """Single-user prototype — returns Aakash's UUID."""
    return DEFAULT_USER_ID


def get_db_conn():
    """Yield a pooled psycopg connection for one request."""
    with _db_get_conn() as conn:
        yield conn
