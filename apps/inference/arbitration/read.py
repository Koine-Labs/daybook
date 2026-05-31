"""Fast-path read seam for L3/L4: get_calibration() from the materialized cache.

Crash-safe (mirrors fusion/loader.py): a missing/unreachable DB or absent row never
raises — it returns a pure cold_start BlendResult (w_personal=0). This is the ONLY
function L3 fusion and L4 prediction should call; they never recompute the weight.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from .blend import BlendResult, CalibrationState
from .constants import default_profile

logger = logging.getLogger(__name__)


def _cold_start(
    axis: str, population_value: float, population_variance: float, *, population_seeded: bool = False
) -> BlendResult:
    return BlendResult(
        axis=axis,
        w_personal=0.0,
        w_population=1.0,
        calibration_state=CalibrationState.COLD_START,
        e_personal=0.0,
        evidence_by_tier={},
        population_value=population_value,
        population_variance=population_variance,
        demographics_applied=False,
        population_seeded=population_seeded,
    )


def get_calibration(user_id: str, axis: str) -> BlendResult:
    """Read the materialized axis_calibration row; lazily seed cold_start if absent."""
    base = default_profile(axis)
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT ac.w_personal, ac.calibration_state, ac.e_personal,
                       COALESCE(cp.population_value, %s),
                       COALESCE(cp.population_variance, %s),
                       ac.demographics_applied,
                       (cp.user_id IS NOT NULL) AS population_seeded
                FROM axis_calibration ac
                LEFT JOIN cold_start_profiles cp
                  ON cp.user_id = ac.user_id AND cp.axis = ac.axis
                WHERE ac.user_id = %s AND ac.axis = %s
                """,
                (base.population_value, base.population_variance, user_id, axis),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "SELECT population_value, population_variance "
                    "FROM cold_start_profiles WHERE user_id = %s AND axis = %s",
                    (user_id, axis),
                )
                prof = cur.fetchone()
                pop_v = prof[0] if prof else base.population_value
                pop_var = prof[1] if prof else base.population_variance
                return _cold_start(axis, pop_v, pop_var, population_seeded=prof is not None)
            w_personal, state, e_personal, pop_v, pop_var, demo_applied, pop_seeded = row
            return BlendResult(
                axis=axis,
                w_personal=w_personal,
                w_population=1.0 - w_personal,
                calibration_state=CalibrationState(state),
                e_personal=e_personal,
                evidence_by_tier={},
                population_value=pop_v,
                population_variance=pop_var,
                demographics_applied=bool(demo_applied),
                population_seeded=bool(pop_seeded),
            )
    except Exception as exc:  # noqa: BLE001 — crash-safe: log + cold_start fallback.
        logger.warning("get_calibration(%s,%s) failed (DB absent or error): %s", user_id, axis, exc)
        return _cold_start(axis, base.population_value, base.population_variance)
