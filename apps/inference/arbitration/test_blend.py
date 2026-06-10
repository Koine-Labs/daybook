"""DB-free + LLM-free tests for the pure arbitration math (blend + state machine)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from arbitration import BlendResult, CalibrationState, blend
from arbitration.blend import calibration_state_for
from arbitration.constants import default_profile
from arbitration.evidence import TierEvidence

NOW = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)


def _tier(tier: str, mass: float, count: int = 1) -> TierEvidence:
    return TierEvidence(tier=tier, count=count, effective_mass=mass, last_observed_at=NOW)


def _blend(tier_evidence: dict[str, TierEvidence], *, prev_state=None):
    return blend(
        "arousal",
        tier_evidence,
        default_profile("arousal"),
        population_value=0.0,
        population_variance=1.0,
        prev_state=prev_state,
        now=NOW,
    )


# --- monotonicity ----------------------------------------------------------

def test_zero_evidence_gives_zero_weight_and_cold_start():
    res = _blend({})
    assert res.w_personal == 0.0
    assert res.w_population == 1.0
    assert res.calibration_state is CalibrationState.COLD_START


def test_more_evidence_is_non_decreasing_weight():
    weights = []
    for mass in [0.0, 1.0, 4.0, 8.0, 100.0, 10_000.0]:
        res = _blend({"self_report": _tier("self_report", mass)})
        weights.append(res.w_personal)
    assert weights == sorted(weights)
    assert all(0.0 <= w < 1.0 for w in weights)


def test_weight_approaches_one_as_evidence_grows():
    res = _blend({"self_report": _tier("self_report", 1e9)})
    assert res.w_personal > 0.999


def test_half_saturation_gives_half_weight():
    e_half = default_profile("arousal").e_half
    res = _blend({"self_report": _tier("self_report", e_half)})
    assert res.w_personal == pytest.approx(0.5, abs=1e-9)


def test_w_population_complements_w_personal():
    res = _blend({"self_report": _tier("self_report", 3.0)})
    assert res.w_personal + res.w_population == pytest.approx(1.0)


# --- e_personal is the tier sum -------------------------------------------

def test_e_personal_sums_tier_masses():
    res = _blend(
        {
            "self_report": _tier("self_report", 2.0),
            "observed_outcome": _tier("observed_outcome", 1.5),
        }
    )
    assert res.e_personal == pytest.approx(3.5)


# --- state machine + hysteresis -------------------------------------------

def test_state_machine_sweep_up():
    p = default_profile("arousal")
    states_up = [calibration_state_for(e, None, p) for e in [0.0, 0.4, 1.0, 5.0, 6.0, 50.0]]
    assert states_up[0] is CalibrationState.COLD_START          # < e_cs_enter
    assert states_up[1] is CalibrationState.COLD_START          # still < e_cs_enter (0.5)
    assert states_up[2] is CalibrationState.CALIBRATING         # >= e_cs_enter, < e_cal_enter
    assert states_up[3] is CalibrationState.CALIBRATING
    assert states_up[4] is CalibrationState.CALIBRATED          # >= e_cal_enter (6.0)
    assert states_up[5] is CalibrationState.CALIBRATED


def test_hysteresis_does_not_flap_coming_down_from_calibrated():
    p = default_profile("arousal")
    # calibrated, evidence drops to 5.0 (below e_cal_enter=6 but above e_cal_exit=4) -> stays calibrated
    assert calibration_state_for(5.0, CalibrationState.CALIBRATED, p) is CalibrationState.CALIBRATED
    # drops below e_cal_exit=4 -> falls to calibrating
    assert calibration_state_for(3.9, CalibrationState.CALIBRATED, p) is CalibrationState.CALIBRATING


def test_hysteresis_does_not_flap_coming_down_from_calibrating():
    p = default_profile("arousal")
    # calibrating, evidence drops to 0.4 (below e_cs_enter=0.5 but above e_cs_exit=0.25) -> stays calibrating
    assert calibration_state_for(0.4, CalibrationState.CALIBRATING, p) is CalibrationState.CALIBRATING
    # drops below e_cs_exit=0.25 -> falls to cold_start
    assert calibration_state_for(0.1, CalibrationState.CALIBRATING, p) is CalibrationState.COLD_START


def test_hysteresis_no_skip_down_two_levels_in_one_step():
    p = default_profile("arousal")
    # from calibrated, even a big drop only steps one level per recompute is NOT required;
    # but a drop straight below cold-start exit must land in cold_start (not stuck).
    assert calibration_state_for(0.0, CalibrationState.CALIBRATED, p) is CalibrationState.COLD_START


def test_blend_uses_prev_state_for_hysteresis():
    p = default_profile("arousal")
    # e=5.0: from cold_start it would be calibrating; from calibrated it stays calibrated.
    cold = _blend({"self_report": _tier("self_report", 5.0)}, prev_state=CalibrationState.COLD_START)
    warm = _blend({"self_report": _tier("self_report", 5.0)}, prev_state=CalibrationState.CALIBRATED)
    assert cold.calibration_state is CalibrationState.CALIBRATING
    assert warm.calibration_state is CalibrationState.CALIBRATED


# --- determinism -----------------------------------------------------------

def test_determinism_same_inputs_same_result():
    ev = {"self_report": _tier("self_report", 3.3)}
    a = _blend(ev)
    b = _blend(ev)
    assert a == b


def test_blend_carries_population_prior_through():
    res = blend(
        "arousal",
        {"self_report": _tier("self_report", 2.0)},
        default_profile("arousal"),
        population_value=0.42,
        population_variance=0.7,
        prev_state=None,
        now=NOW,
        demographics_applied=True,
    )
    assert res.population_value == 0.42
    assert res.population_variance == 0.7
    assert res.demographics_applied is True
    assert isinstance(res, BlendResult)
