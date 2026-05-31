"""Pure arbitration heart: blend() -> BlendResult (weight + calibration_state).

No DB, no clock-of-its-own, no network. `now` is injected for testability. The
calibration_state machine has hysteresis (it does not flap on the way down).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .constants import ProfileParams
from .evidence import TierEvidence


class CalibrationState(str, Enum):
    """Coarse, surfaced-to-the-user view of personal-evidence accumulation."""

    COLD_START = "cold_start"
    CALIBRATING = "calibrating"
    CALIBRATED = "calibrated"


@dataclass(frozen=True)
class BlendResult:
    """Population<->personal mixing weight + calibration_state + diagnostics."""

    axis: str
    w_personal: float
    w_population: float
    calibration_state: CalibrationState
    e_personal: float
    evidence_by_tier: dict[str, TierEvidence]
    population_value: float
    population_variance: float
    demographics_applied: bool


def calibration_state_for(
    e_personal: float,
    prev_state: CalibrationState | None,
    profile: ProfileParams,
) -> CalibrationState:
    """Map effective evidence mass -> calibration_state with hysteresis.

    Rising uses the *enter* thresholds; falling from a higher state requires
    dropping below the lower *exit* thresholds, so the state does not flap.
    """
    # Rising / first-evaluation thresholds.
    if prev_state is None:
        if e_personal >= profile.e_cal_enter:
            return CalibrationState.CALIBRATED
        if e_personal >= profile.e_cs_enter:
            return CalibrationState.CALIBRATING
        return CalibrationState.COLD_START

    if prev_state is CalibrationState.CALIBRATED:
        # Stay calibrated until evidence falls below the calibrated-exit floor.
        if e_personal >= profile.e_cal_exit:
            return CalibrationState.CALIBRATED
        # Dropped below cal_exit: fall — but possibly all the way to cold_start.
        if e_personal >= profile.e_cs_exit:
            return CalibrationState.CALIBRATING
        return CalibrationState.COLD_START

    if prev_state is CalibrationState.CALIBRATING:
        # Can rise to calibrated on the enter threshold.
        if e_personal >= profile.e_cal_enter:
            return CalibrationState.CALIBRATED
        # Stay calibrating until below the calibrating-exit floor.
        if e_personal >= profile.e_cs_exit:
            return CalibrationState.CALIBRATING
        return CalibrationState.COLD_START

    # prev_state is COLD_START: rise on the enter thresholds.
    if e_personal >= profile.e_cal_enter:
        return CalibrationState.CALIBRATED
    if e_personal >= profile.e_cs_enter:
        return CalibrationState.CALIBRATING
    return CalibrationState.COLD_START


def blend(
    axis: str,
    tier_evidence: dict[str, TierEvidence],
    profile: ProfileParams,
    population_value: float,
    population_variance: float,
    *,
    prev_state: CalibrationState | None = None,
    now: datetime,
    demographics_applied: bool = False,
) -> BlendResult:
    """Pure. Combine per-tier evidence into w_personal + calibration_state."""
    e_personal = sum(te.effective_mass for te in tier_evidence.values())
    denom = e_personal + profile.e_half
    w_personal = 0.0 if denom <= 0.0 else e_personal / denom
    state = calibration_state_for(e_personal, prev_state, profile)
    return BlendResult(
        axis=axis,
        w_personal=w_personal,
        w_population=1.0 - w_personal,
        calibration_state=state,
        e_personal=e_personal,
        evidence_by_tier=dict(tier_evidence),
        population_value=population_value,
        population_variance=population_variance,
        demographics_applied=demographics_applied,
    )
