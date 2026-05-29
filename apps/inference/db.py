"""Database connection helper for Daybook's Python pipeline.

Loads DATABASE_URL from the inference workspace's `.env.local` file (gitignored).
Provides a process-wide connection pool and a `get_conn()` context manager
that yields a single connection from the pool.

Usage:
    from db import get_conn

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from dotenv import load_dotenv
from psycopg import Connection
from psycopg_pool import ConnectionPool

# Load .env.local from the inference workspace root (where this file lives).
ENV_PATH = Path(__file__).parent / ".env.local"
load_dotenv(ENV_PATH)

# Resolved at import (may be None). The requirement is enforced lazily at pool
# creation — importing this module must never require runtime config, so the
# L1–L6 protocol/bus core stays import-safe and DB-free under test.
DATABASE_URL = os.environ.get("DATABASE_URL")

# Process-wide connection pool. Lazy-initialized on first use.
_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError(
                f"DATABASE_URL not found. Expected in {ENV_PATH} (gitignored) or env var."
            )
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=1,
            max_size=4,  # Conservative for v0; raise when API endpoints arrive
            open=True,
            kwargs={"autocommit": False},
        )
    return _pool


@contextmanager
def get_conn() -> Iterator[Connection]:
    """Yield a connection from the pool.

    The pool's `connection()` context manager commits on clean exit and
    rolls back on exception. Caller can also commit/rollback explicitly.
    """
    pool = _get_pool()
    with pool.connection() as conn:
        yield conn


def close_pool() -> None:
    """Cleanly shut down the pool. Call at process exit (or use atexit)."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
