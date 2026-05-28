"""Load the current per-user BeliefState from user_state_estimate rows."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import get_conn  # noqa: E402

from .belief_state import AxisEstimate, BeliefState


def load_belief_state(user_id: str, *, now: datetime | None = None) -> BeliefState:
    """Latest per-axis row -> AxisEstimate, bundled into a BeliefState.

    Freshness is NOT filtered here -- callers use BeliefState.get()/snapshot(),
    which apply each axis's freshness gate. `now` is accepted for test
    determinism.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    belief = BeliefState(user_id=user_id)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (axis)
                axis, value, confidence, source, timestamp, meta_context, i_model_id
            FROM user_state_estimate
            WHERE user_id = %s
            ORDER BY axis, timestamp DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    for axis, value, confidence, source, ts, meta_context, i_model_id in rows:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        belief.update(
            AxisEstimate(
                axis=axis,
                value=value if isinstance(value, dict) else {"value": value},
                timestamp=ts,
                confidence=confidence,
                source=source or "unknown",
                meta_context=meta_context,
                i_model_id=str(i_model_id) if i_model_id is not None else None,
            )
        )
    return belief
