"""Universal gesture/action recorder — writes a user_actions row."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

INFERENCE_DIR = Path(__file__).resolve().parent.parent / "inference"
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402


def record_action(
    *,
    user_id: str,
    kind: str,
    source: str,
    intent: str | None = None,
    context: dict | None = None,
    triggered_by: str | None = None,
) -> str:
    """Insert a user_actions row. Returns new action id."""
    payload = context or {}
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_actions
                (user_id, occurred_at, kind, source, intent, context, triggered_by)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
            RETURNING id
            """,
            (
                user_id,
                datetime.now(timezone.utc),
                kind,
                source,
                intent,
                json.dumps(payload, default=str),
                triggered_by,
            ),
        )
        new_id = str(cur.fetchone()[0])
        conn.commit()
    return new_id
