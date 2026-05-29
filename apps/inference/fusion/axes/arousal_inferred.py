"""L3 axis: arousal_inferred — biometric HR/HRV -> a [0,1] physiological arousal estimate.

v1 heuristic scaffold (linear HR + inverse-HRV map). NOT a trained classifier and
NOT personalized: calibration constants are documented placeholders, not fitted to
Aakash's physiology, and there is no personal resting baseline on the bus yet — the
estimate is population-style, NOT "deviation from your norm". This axis exists to
generate the data flywheel toward the JEPA-era latent world model (commitment #16);
it is a stand-alone per-axis scaffold per ARCHITECTURE §2.16's v1 plan, designed to
compose forward, not be thrown away. Pure, DB-free.

Live-only: a biometric_window FeatureSnapshot rides TOPIC_FEATURE, but there is no
"biometric-window-as-axis" sensor-table persistence path, so there is intentionally
NO DB fuse_recent fallback (a documented follow-on if these windows are persisted).

meta_context deferral (#14): this axis tags meta_context=None — it genuinely cannot
tell SLEEP from WAKING. The biometric snapshot's meta_context_hint is None and the
envelope never reaches fuse_from_feature, and the SAME biometric stream flows under
BOTH meta-contexts (unlike cognitive_load/visual_context, by-construction waking-only
EEG/cam streams that legitimately tag "waking"). The raw hr_mean/hrv_mean/
hr_pct_above_baseline are exposed in value precisely so the downstream layer that DOES
hold the envelope meta_context (L4/L5, the way prediction/feature_participant.py reads
inbound.meta_context for the REM SLEEP-gate) can reinterpret "high HR" as waking
exertion vs sleep micro-arousal — without re-reading the biometrics. The "no arousal
inference during deep sleep" suppression also defers to L5/L6 channel selection,
identical to cognitive_load/visual_context — convention, not code enforced here.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from ..belief_state import AxisEstimate

AXIS = "arousal_inferred"
SOURCE = "L3.fusion.arousal_inferred.v1_heuristic"
FRESH_SECONDS = 120  # physiology shifts fast; matches cognitive_load/meta_context, < sleep_stage's 600s
KIND = "biometric_window"

# v1 calibration placeholders — NOT fitted to Aakash's physiology. Flagged for the
# EXG-Pill / real-watch calibration step, exactly like cognitive_load's _ENGAGE_LO/_HI.
HR_LO, HR_HI = 55.0, 110.0     # bpm: resting-ish floor -> exertion ceiling
HRV_LO, HRV_HI = 20.0, 70.0    # ms (RMSSD-style): low HRV -> high sympathetic arousal


def _num(features: dict, key: str) -> float | None:
    """NaN-safe scalar read: None if missing or NaN."""
    v = features.get(key)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _band(arousal: float) -> str:
    return "low" if arousal < 0.34 else ("medium" if arousal < 0.67 else "high")


def _trend(hr_slope: float | None) -> str:
    if hr_slope is None or hr_slope == 0.0:
        return "flat"
    return "rising" if hr_slope > 0.0 else "falling"


def fuse_from_feature(packet, *, now: datetime | None = None) -> AxisEstimate | None:
    """Build a live arousal_inferred estimate from an L2 biometric FeatureSnapshot, else None.

    Only fires for our own kind (biometric_window); other kinds/modalities return
    None so the participant records arousal_inferred as OFFLINE. No DB.

    BLOCKING FIX #1: the scalar uses ONLY within-window physiologically-meaningful
    features (hr_mean, inverse hrv_mean). hr_pct_above_baseline is near-constant
    within-window dispersion on the live single-window path (no arousal-level info),
    so it is EXPOSED in value (baseline="in_window_only") but NEVER weighted into the
    number — weighting it would inject a constant bias and waste weight on noise.
    """
    feats = getattr(packet, "payload", {}) or {}
    if feats.get("kind") != KIND:
        return None
    f = feats.get("features", {}) or {}

    hr_mean = _num(f, "hr_mean")
    hrv_mean = _num(f, "hrv_mean")
    hr_slope = _num(f, "hr_slope")
    hr_pct_above_baseline = _num(f, "hr_pct_above_baseline")

    if hr_mean is None and hrv_mean is None:  # no usable signal -> OFFLINE upstream
        return None

    weight, contrib = 0.0, 0.0
    if hr_mean is not None:
        hr_component = _clamp((hr_mean - HR_LO) / (HR_HI - HR_LO))
        weight += 0.6
        contrib += 0.6 * hr_component
    if hrv_mean is not None:
        hrv_component = _clamp((HRV_HI - hrv_mean) / (HRV_HI - HRV_LO))  # inverse: low HRV -> high arousal
        weight += 0.4
        contrib += 0.4 * hrv_component
    arousal = _clamp(contrib / weight)  # renormalize over present components

    return AxisEstimate(
        axis=AXIS,
        value={
            "arousal": round(arousal, 3),               # [0,1] scalar
            "band": _band(arousal),                     # "low" | "medium" | "high"
            "hr_mean": hr_mean,
            "hrv_mean": hrv_mean,
            "hr_pct_above_baseline": hr_pct_above_baseline,  # exposed, NOT weighted (FIX #1)
            "hr_trend": _trend(hr_slope),               # "rising" | "falling" | "flat"; not in scalar
            "method": "biometric_arousal_linear_v1",
            "scaffold": True,                            # explicit: not a trained model
            "baseline": "in_window_only",                # honest: no personal resting baseline yet
            "meta_context_aware": False,                 # honest: cannot tell SLEEP from WAKING (#14)
        },
        timestamp=getattr(packet, "timestamp", None) or now or datetime.now(timezone.utc),
        confidence=0.4,                                  # low — honest for an unfitted heuristic
        source=SOURCE,
        meta_context=None,                               # MANDATORY: packet lacks the frame (#14)
        fresh_for_seconds=FRESH_SECONDS,
    )
