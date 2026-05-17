from __future__ import annotations

import logging
from datetime import datetime, timezone

from config import ensure_inference_importable

ensure_inference_importable()
from db import get_conn  # noqa: E402

logger = logging.getLogger(__name__)


def create_session(user_id: str, started_at: datetime, expected_seconds: int = 8 * 3600) -> str:
    """Insert a sleep_sessions row, return its UUID as str."""
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    # ended_at + duration_seconds get filled at session close; for now use planned values.
    placeholder_end = started_at + (started_at - started_at)  # = started_at, updated on close
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sleep_sessions
                (user_id, started_at, ended_at, duration_seconds, sensor_sources)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, started_at, started_at, expected_seconds, ["daybook_pi_v0"]),
        )
        row = cur.fetchone()
        conn.commit()
    sid = str(row[0])
    logger.info("Created session %s (user=%s started=%s)", sid, user_id, started_at.isoformat())
    return sid


def close_session(session_id: str, ended_at: datetime) -> None:
    """Update sleep_sessions row to mark it ended."""
    if ended_at.tzinfo is None:
        ended_at = ended_at.replace(tzinfo=timezone.utc)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE sleep_sessions
            SET ended_at = %s,
                duration_seconds = EXTRACT(EPOCH FROM (%s - started_at))::INTEGER
            WHERE id = %s
            """,
            (ended_at, ended_at, session_id),
        )
        conn.commit()
    logger.info("Closed session %s at %s", session_id, ended_at.isoformat())
