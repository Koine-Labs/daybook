"""meta_context axis fusion — coarse waking sub-state from Mac sensors.

v1 fixed-heuristic. Learned categorization post-MVP. See Week-1 plan for
the rule table.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

INF_DIR = Path(__file__).resolve().parent.parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from ..belief_state import AxisEstimate

CODING_APPS = {
    "Cursor", "Terminal", "iTerm", "Code", "Visual Studio Code",
    "IntelliJ IDEA", "PyCharm", "Xcode", "Sublime Text", "Vim", "Neovim", "Zed",
}
COMMUNICATING_APPS = {
    "Mail", "Slack", "Discord", "Messages", "Telegram", "Microsoft Teams",
    "WhatsApp", "Signal", "Zoom",
}
CONSUMING_APPS = {
    "YouTube", "Netflix", "Spotify", "Music", "Apple TV", "TV", "Hulu", "Twitch",
}
BROWSING_APPS = {"Safari", "Chrome", "Google Chrome", "Firefox", "Arc", "Edge", "Brave Browser"}

IDLE_THRESHOLD_S = 300
ACTIVE_IDLE_MAX_S = 60

SOURCE = "L3.fusion.meta_context.v1_heuristic"


def classify_meta_context(*, active_app: str, idle_seconds: float) -> dict[str, Any]:
    """Apply v1 heuristic. Returns {category, reason}."""
    if idle_seconds > IDLE_THRESHOLD_S:
        return {"category": "waking/idle", "reason": f"idle {int(idle_seconds)}s > {IDLE_THRESHOLD_S}s"}

    if active_app in CODING_APPS and idle_seconds < ACTIVE_IDLE_MAX_S:
        return {"category": "waking/focused", "reason": f"coding app + active <{ACTIVE_IDLE_MAX_S}s idle"}

    if active_app in COMMUNICATING_APPS:
        return {"category": "waking/communicating", "reason": "communication app"}

    if active_app in CONSUMING_APPS:
        return {"category": "waking/consuming", "reason": "media app"}

    if active_app in BROWSING_APPS:
        return {"category": "waking/browsing", "reason": "browser"}

    return {"category": "waking/other", "reason": f"unrecognized app: {active_app}"}


def fuse_recent(
    *,
    user_id: str,
    now: datetime | None = None,
    window_seconds: int = 60,
) -> AxisEstimate | None:
    """Pull the latest mac_activity reading in window_seconds and classify.

    Returns None if no Mac sensor data is present in the window.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=window_seconds)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT recorded_at, payload
            FROM sensor_readings
            WHERE user_id = %s
              AND kind = 'mac_activity'
              AND recorded_at >= %s
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (user_id, window_start),
        )
        row = cur.fetchone()

    if row is None:
        return None

    ts, payload = row
    active_app = payload.get("active_app", "unknown")
    idle_seconds = float(payload.get("idle_seconds", 0))

    cls = classify_meta_context(active_app=active_app, idle_seconds=idle_seconds)
    return AxisEstimate(
        axis="meta_context",
        value=cls,
        timestamp=ts,
        confidence=0.65,  # v1 heuristic — moderate confidence
        source=SOURCE,
        meta_context=cls["category"],
        fresh_for_seconds=120,
    )
