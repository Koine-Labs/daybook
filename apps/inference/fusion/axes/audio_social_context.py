"""L3 axis: audio_social_context — is the user alone or with others, by ear."""
from __future__ import annotations

import sys
from datetime import timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from ..belief_state import AxisEstimate

AXIS = "audio_social_context"
SOURCE = "L3.fusion.audio_social_context"
FRESH_SECONDS = 300


def compute_audio_social_context(user_id: str) -> AxisEstimate | None:
    """Latest audio_social_context packet → alone/with_other estimate, or None."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT payload, recorded_at
            FROM sensor_readings
            WHERE user_id = %s AND kind = 'audio_social_context'
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    payload, recorded_at = row
    speaker = (payload or {}).get("speaker", "none")
    category = "with_other" if speaker in ("other", "both") else "alone"
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    return AxisEstimate(
        axis=AXIS,
        value={"category": category},
        timestamp=recorded_at,
        confidence=0.8,
        source=SOURCE,
        meta_context=None,
        fresh_for_seconds=FRESH_SECONDS,
    )
