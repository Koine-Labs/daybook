"""Tests for L3 calibration enrichment (commitment #4 wire-up into fusion)."""
from __future__ import annotations

from datetime import datetime, timezone

from arbitration.blend import BlendResult, CalibrationState
from fusion.belief_state import AxisEstimate
from fusion.calibration import apply_calibration


def _est(axis: str = "arousal_inferred", value: dict | None = None) -> AxisEstimate:
    return AxisEstimate(
        axis=axis,
        value=value if value is not None else {"arousal": 0.7, "band": "high"},
        timestamp=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
        confidence=0.4,
        source="L3.fusion.arousal_inferred.v1_heuristic",
    )


def _calib(
    *, state=CalibrationState.COLD_START, w_personal=0.0, pop_value=0.0, seeded=False
) -> BlendResult:
    return BlendResult(
        axis="arousal_inferred",
        w_personal=w_personal,
        w_population=1.0 - w_personal,
        calibration_state=state,
        e_personal=0.0,
        evidence_by_tier={},
        population_value=pop_value,
        population_variance=1.0,
        demographics_applied=False,
        population_seeded=seeded,
    )


def test_attaches_calibration_state_metadata() -> None:
    out = apply_calibration(_est(), _calib(state=CalibrationState.CALIBRATING))
    assert out.value["calibration_state"] == "calibrating"
    assert out.value["w_personal"] == 0.0


def test_offline_estimate_is_returned_untouched() -> None:
    offline = AxisEstimate(
        axis="arousal_inferred",
        value={"category": "offline", "reason": "no fresh data"},
        timestamp=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
        confidence=None,
        source="L3.fusion.arousal_inferred.offline",
        fresh_for_seconds=-1,
    )
    out = apply_calibration(offline, _calib())
    assert out is offline  # never enrich a degraded sentinel


def test_no_blend_when_population_unseeded() -> None:
    # cold_start_profiles empty: population_value is a 0.0 placeholder. Must NOT
    # drag a real 0.7 reading toward zero. Scalar stays put.
    out = apply_calibration(_est(), _calib(w_personal=0.0, pop_value=0.0, seeded=False))
    assert out.value["arousal"] == 0.7
    assert out.value.get("blended") is not True


def test_blends_toward_population_only_when_seeded() -> None:
    # seeded population pole = 0.3, w_personal 0.5 -> 0.5*0.7 + 0.5*0.3 = 0.5
    out = apply_calibration(
        _est(), _calib(w_personal=0.5, pop_value=0.3, seeded=True)
    )
    assert abs(out.value["arousal"] - 0.5) < 1e-9
    assert out.value["blended"] is True


def test_seeded_but_no_numeric_scalar_is_safe() -> None:
    # a categorical axis value (no float to blend) must not crash; metadata still attaches.
    out = apply_calibration(
        _est(value={"category": "drowsy"}),
        _calib(w_personal=0.5, pop_value=0.3, seeded=True),
    )
    assert out.value["calibration_state"] == "cold_start"
    assert out.value["category"] == "drowsy"


def test_original_estimate_not_mutated() -> None:
    est = _est()
    apply_calibration(est, _calib(state=CalibrationState.CALIBRATED))
    assert "calibration_state" not in est.value  # enrichment returns a copy
