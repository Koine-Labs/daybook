"""L3 axis: audio_social_context — is the user alone or with others, by ear."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from ..belief_state import AxisEstimate

AXIS = "audio_social_context"
SOURCE = "L3.fusion.audio_social_context.v1"
FRESH_SECONDS = 300


def fuse_from_feature(packet, *, now: datetime | None = None) -> AxisEstimate | None:
    """Build a live estimate from an L2 audio FeatureSnapshot, else None.

    Only fires for our own kind (audio_social_context); other kinds/modalities
    return None so the participant falls back to the DB fuse_recent path. No DB.
    """
    feats = getattr(packet, "payload", {}) or {}
    if feats.get("kind") != "audio_social_context":
        return None
    category = feats.get("social_category")
    if category is None:
        category = "with_other" if feats.get("speaker") in ("other", "both") else "alone"
    return AxisEstimate(
        axis=AXIS,
        value={"category": category},
        timestamp=getattr(packet, "timestamp", None) or now or datetime.now(timezone.utc),
        confidence=0.8,
        source=SOURCE + ".live",
        meta_context=None,
        fresh_for_seconds=FRESH_SECONDS,
    )


def fuse_recent(
    *,
    user_id: str,
    now: datetime | None = None,
    window_seconds: int = FRESH_SECONDS,
) -> AxisEstimate | None:
    """Latest audio_social_context packet in window → alone/with_other, or None."""
    if now is None:
        now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=window_seconds)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT payload, recorded_at
            FROM sensor_readings
            WHERE user_id = %s
              AND kind = 'audio_social_context'
              AND recorded_at >= %s
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (user_id, window_start),
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
