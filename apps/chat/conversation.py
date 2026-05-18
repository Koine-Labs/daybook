"""Conversation lifecycle: create, find recent, resume."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402


RESUME_WINDOW = timedelta(hours=1)


def create_conversation(*, user_id: str, title: str | None = None) -> str:
    """Insert a new chat_conversations row. Returns its id."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_conversations (user_id, title)
            VALUES (%s, %s)
            RETURNING id
            """,
            (user_id, title),
        )
        new_id = str(cur.fetchone()[0])
        conn.commit()
    return new_id


def most_recent_conversation(
    *, user_id: str, within: timedelta = RESUME_WINDOW
) -> str | None:
    """Return the most-recent conversation id if its last activity is within `within`."""
    cutoff = datetime.now(timezone.utc) - within
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id
            FROM chat_conversations c
            LEFT JOIN chat_messages m ON m.conversation_id = c.id
            WHERE c.user_id = %s
              AND c.ended_at IS NULL
            GROUP BY c.id, c.started_at
            HAVING COALESCE(MAX(m.sent_at), c.started_at) >= %s
            ORDER BY COALESCE(MAX(m.sent_at), c.started_at) DESC
            LIMIT 1
            """,
            (user_id, cutoff),
        )
        row = cur.fetchone()
    return str(row[0]) if row else None


def most_recent_conversation_within(
    user_id: str, minutes: int = 30
) -> str | None:
    """Convenience: resume if last activity was within `minutes`. Default 30."""
    return most_recent_conversation(
        user_id=user_id, within=timedelta(minutes=minutes)
    )


def start_or_resume_conversation(
    *, user_id: str, force_new: bool = False, title: str | None = None
) -> str:
    """Return an existing recent conversation if one exists, else create a fresh one."""
    if not force_new:
        existing = most_recent_conversation(user_id=user_id)
        if existing:
            return existing
    return create_conversation(user_id=user_id, title=title)


def end_conversation(*, conversation_id: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE chat_conversations SET ended_at = NOW() WHERE id = %s",
            (conversation_id,),
        )
        conn.commit()


def set_conversation_title(*, conversation_id: str, title: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE chat_conversations SET title = %s WHERE id = %s",
            (title, conversation_id),
        )
        conn.commit()
