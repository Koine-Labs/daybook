"""Per-axis-row writer for user_state_estimate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from .belief_state import AxisEstimate


def write_axis_estimate(user_id: str, est: AxisEstimate) -> str:
    """Insert one per-axis-row into user_state_estimate. Returns new id."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_state_estimate
              (user_id, axis, timestamp, value, confidence, source, meta_context, i_model_id)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id,
                est.axis,
                est.timestamp,
                json.dumps(est.value),
                est.confidence,
                est.source,
                est.meta_context,
                est.i_model_id,
            ),
        )
        new_id = str(cur.fetchone()[0])
        conn.commit()
    return new_id
