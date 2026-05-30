"""sleep_stage axis fusion — current sleep stage from Apple Health labels.

Reads the most recent `apple_health_sleep_stage` row whose [start,end] window
covers `now`. Emits OFFLINE (returns None) if no such window.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INF_DIR = Path(__file__).resolve().parent.parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from ..belief_state import AxisEstimate

# Stages where the user is actually asleep (vs. just in bed or awake-in-bed).
ACTIVE_SLEEP_STAGES = {"core", "deep", "rem", "asleep", "asleep_legacy"}

SOURCE = "apple_health_sleep_stage"


def classify_sleep_stage(*, stage: str, duration_s: int, source: str) -> dict[str, Any]:
    """Wrap an Apple Health sleep label into our axis value shape."""
    return {
        "label": stage,
        "active": stage in ACTIVE_SLEEP_STAGES,
        "duration_s": duration_s,
        "source": source,
    }


def fuse_recent(
    *,
    user_id: str,
    now: datetime | None = None,
) -> AxisEstimate | None:
    """Find the apple_health_sleep_stage row whose [start, end] covers `now`.

    Returns AxisEstimate if covered; None otherwise (= OFFLINE).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT recorded_at, payload
            FROM sensor_readings
            WHERE user_id = %s
              AND kind = 'apple_health_sleep_stage'
              AND recorded_at <= %s
              AND (payload->>'end')::timestamptz >= %s
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (user_id, now, now),
        )
        row = cur.fetchone()

    if row is None:
        return None

    ts, payload = row
    cls = classify_sleep_stage(
        stage=payload.get("stage", "unknown"),
        duration_s=int(payload.get("duration_s", 0)),
        source=payload.get("source", ""),
    )
    return AxisEstimate(
        axis="sleep_stage",
        value=cls,
        timestamp=ts,
        confidence=0.95,  # AH labels are direct watch output
        source=SOURCE,
        meta_context="sleep" if cls["active"] else None,
        fresh_for_seconds=600,  # 10min — stages are slow
    )
