"""Impure single-writer seam: recompute_axis() — reads ledger + DB, writes cache.

Crash-safe (mirrors fusion/writer.py + loader.py + labels/ledger.py): a missing or
unreachable DB never raises — it logs a warning and falls back to a pure cold_start
result. `get_conn` and `read_labels` are module-level names so tests can monkeypatch
them; the real `get_conn` is imported at module load behind the sys.path shim, but
no DB call happens until a function runs.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402
from labels import LabelSource, read_labels  # noqa: E402

from .blend import BlendResult, CalibrationState, blend
from .constants import PERSONAL_TIERS, ProfileParams, default_profile
from .demographics import ConsentedCohort, DemographicModifier, apply
from .evidence import summarize

logger = logging.getLogger(__name__)

_PERSONAL_SOURCES = sorted(t.value for t in PERSONAL_TIERS)


def _profile_from_row(axis: str, row) -> ProfileParams:
    """Build a ProfileParams from a cold_start_profiles row, falling back to defaults."""
    if row is None:
        return default_profile(axis)
    (pop_v, pop_var, lit_src, e_half, e_cs_enter, e_cs_exit,
     e_cal_enter, e_cal_exit, tier_trust, tier_halflife_s, _prev) = (
        row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9],
        row[10] if len(row) > 10 else None,
    )
    base = default_profile(axis)
    return ProfileParams(
        axis=axis,
        population_value=pop_v if pop_v is not None else base.population_value,
        population_variance=pop_var if pop_var is not None else base.population_variance,
        literature_source=lit_src,
        e_half=e_half if e_half is not None else base.e_half,
        e_cs_enter=e_cs_enter if e_cs_enter is not None else base.e_cs_enter,
        e_cs_exit=e_cs_exit if e_cs_exit is not None else base.e_cs_exit,
        e_cal_enter=e_cal_enter if e_cal_enter is not None else base.e_cal_enter,
        e_cal_exit=e_cal_exit if e_cal_exit is not None else base.e_cal_exit,
        tier_trust=_as_dict(tier_trust, base.tier_trust),
        tier_halflife_s=_as_dict(tier_halflife_s, base.tier_halflife_s),
        tier_saturation=dict(base.tier_saturation),
    )


def _as_dict(raw, fallback: dict) -> dict:
    if raw is None:
        return dict(fallback)
    if isinstance(raw, dict):
        return {k: float(v) for k, v in raw.items()}
    try:
        return {k: float(v) for k, v in json.loads(raw).items()}
    except Exception:  # noqa: BLE001 — malformed json -> fall back to defaults.
        return dict(fallback)


def _evidence_json(evidence_by_tier) -> str:
    out = {}
    for tier, te in evidence_by_tier.items():
        out[tier] = {
            "count": te.count,
            "effective_mass": te.effective_mass,
            "last_observed_at": te.last_observed_at.isoformat() if te.last_observed_at else None,
        }
    return json.dumps(out)


def recompute_axis(user_id: str, axis: str, *, now: datetime | None = None) -> BlendResult:
    """Recompute + materialize axis_calibration for (user, axis). Crash-safe.

    Single source of truth: reads the ledger via read_labels, summarizes evidence,
    applies opt-in demographics, blends, UPSERTs axis_calibration, and appends an
    axis_calibration_history row when the state changes. Returns the BlendResult.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    label_rows = read_labels(user_id, axis=axis, sources=_PERSONAL_SOURCES)

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT population_value, population_variance, literature_source,
                       e_half, e_cs_enter, e_cs_exit, e_cal_enter, e_cal_exit,
                       tier_trust, tier_halflife_s
                FROM cold_start_profiles WHERE user_id = %s AND axis = %s
                """,
                (user_id, axis),
            )
            profile = _profile_from_row(axis, cur.fetchone())

            cur.execute(
                "SELECT calibration_state FROM axis_calibration WHERE user_id = %s AND axis = %s",
                (user_id, axis),
            )
            prev_row = cur.fetchone()
            prev_state = CalibrationState(prev_row[0]) if prev_row and prev_row[0] else None

            cur.execute(
                "SELECT cohort_key, cohort_value FROM user_demographics "
                "WHERE user_id = %s AND consented = true",
                (user_id,),
            )
            consented = [ConsentedCohort(k, v) for k, v in (cur.fetchall() or [])]
            modifiers = _load_modifiers(cur, axis) if consented else []

            pop_v, pop_var, applied = apply(
                profile.population_value, profile.population_variance, consented, modifiers
            )
            tier_evidence = summarize(label_rows, profile, now=now)
            result = blend(
                axis, tier_evidence, profile, pop_v, pop_var,
                prev_state=prev_state, now=now, demographics_applied=applied,
            )

            _upsert(cur, user_id, axis, result, now)
            if prev_state is None or prev_state != result.calibration_state:
                _append_history(cur, user_id, axis, result, prev_state)
            conn.commit()
            return result
    except Exception as exc:  # noqa: BLE001 — crash-safe: log + pure fallback.
        logger.warning("recompute_axis(%s,%s) failed (DB absent or error): %s", user_id, axis, exc)
        profile = default_profile(axis)
        tier_evidence = summarize(label_rows, profile, now=now)
        return blend(
            axis, tier_evidence, profile,
            profile.population_value, profile.population_variance, now=now,
        )


def _load_modifiers(cur, axis: str) -> list[DemographicModifier]:
    cur.execute(
        "SELECT axis, cohort_key, cohort_value, value_shift, variance_scale, "
        "max_abs_shift, source, enabled, bias_notes "
        "FROM demographic_priors WHERE axis = %s AND enabled = true",
        (axis,),
    )
    rows = cur.fetchall() or []
    return [
        DemographicModifier(
            axis=r[0], cohort_key=r[1], cohort_value=r[2], value_shift=r[3],
            variance_scale=r[4], max_abs_shift=r[5], source=r[6],
            enabled=bool(r[7]), bias_notes=r[8],
        )
        for r in rows
    ]


def _upsert(cur, user_id: str, axis: str, result: BlendResult, now: datetime) -> None:
    cur.execute(
        """
        INSERT INTO axis_calibration
          (user_id, axis, w_personal, calibration_state, e_personal,
           evidence_by_tier, demographics_applied, computed_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
        ON CONFLICT (user_id, axis) DO UPDATE SET
          w_personal = EXCLUDED.w_personal,
          calibration_state = EXCLUDED.calibration_state,
          e_personal = EXCLUDED.e_personal,
          evidence_by_tier = EXCLUDED.evidence_by_tier,
          demographics_applied = EXCLUDED.demographics_applied,
          computed_at = EXCLUDED.computed_at,
          updated_at = EXCLUDED.updated_at
        """,
        (
            user_id, axis, result.w_personal, result.calibration_state.value,
            result.e_personal, _evidence_json(result.evidence_by_tier),
            result.demographics_applied, now, now,
        ),
    )


def _append_history(cur, user_id: str, axis: str, result: BlendResult,
                    prev_state: CalibrationState | None) -> None:
    reason = "state_transition" if prev_state is not None else "recompute"
    cur.execute(
        """
        INSERT INTO axis_calibration_history
          (user_id, axis, w_personal, calibration_state, prev_state,
           e_personal, evidence_by_tier, reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        """,
        (
            user_id, axis, result.w_personal, result.calibration_state.value,
            prev_state.value if prev_state else None,
            result.e_personal, _evidence_json(result.evidence_by_tier), reason,
        ),
    )
