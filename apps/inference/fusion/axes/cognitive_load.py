"""L3 axis: cognitive_load — band-power derived features -> a [0,1] load estimate.

v1 heuristic scaffold (engagement-index linear map). NOT a trained classifier.
Normalization constants are documented placeholders, not fitted. This axis exists
to generate the data flywheel toward the JEPA-era latent world model (commitment
#16); it is a stand-alone per-axis scaffold per ARCHITECTURE §2.16's v1 plan,
designed to compose forward, not be thrown away.

cognitive_load is a WAKING sub-context signal (#14). Live-only: there is no
eeg_bandpower sensor-table persistence path yet, so there is intentionally NO DB
fuse_recent fallback (a documented follow-on for when EEG band-powers are
persisted to sensor_readings). Pure, DB-free.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..belief_state import AxisEstimate

AXIS = "cognitive_load"
SOURCE = "L3.fusion.cognitive_load.v1_heuristic"
FRESH_SECONDS = 120  # EEG state shifts fast; matches meta_context's 120s, < sleep_stage's 600s

# v1 normalization constants (documented placeholders — NOT fitted).
# engagement_index = beta/(alpha+theta); empirical waking range ~0.1 (idle) upward.
# _ENGAGE_HI=1.0 is the clamp ceiling, so any engagement_index >= 1.0 saturates to
# load=1.0 — intentional for an unfitted v1 scaffold; the EXG-Pill calibration step
# fits both constants (see bci/firmware/eeg_edge_stub.py CALIBRATION-ON-ARRIVAL).
_ENGAGE_LO, _ENGAGE_HI = 0.15, 1.0


def _load_scalar(features: dict) -> float | None:
    e = features.get("engagement_index")
    if e is None:
        return None
    # linear clamp into [0,1]; high engagement -> high load
    return max(0.0, min(1.0, (e - _ENGAGE_LO) / (_ENGAGE_HI - _ENGAGE_LO)))


def _band(load: float) -> str:
    return "low" if load < 0.34 else ("medium" if load < 0.67 else "high")


def fuse_from_feature(packet, *, now: datetime | None = None) -> AxisEstimate | None:
    """Build a live cognitive_load estimate from an L2 BCI FeatureSnapshot, else None.

    Only fires for our own kind (eeg_bandpower); other kinds/modalities return None
    so the participant records cognitive_load as OFFLINE. No DB.

    This axis does NOT itself gate on the active meta-context — it fires for any
    eeg_bandpower window. #14's "no EEG-load inference during deep sleep" gating is
    deferred to a downstream layer (L5/L6 channel selection), not enforced here.
    """
    feats = getattr(packet, "payload", {}) or {}
    if feats.get("kind") != "eeg_bandpower":
        return None
    derived = feats.get("features", {}) or {}
    load = _load_scalar(derived)
    if load is None:  # no usable engagement signal -> OFFLINE upstream
        return None
    return AxisEstimate(
        axis=AXIS,
        value={
            "load": round(load, 3),                 # [0,1] scalar
            "band": _band(load),                    # "low" | "medium" | "high"
            "engagement_index": derived.get("engagement_index"),
            "theta_beta_ratio": derived.get("theta_beta_ratio"),
            "method": "engagement_index_linear_v1",
            "scaffold": True,                        # explicit: not a trained model
        },
        timestamp=getattr(packet, "timestamp", None) or now or datetime.now(timezone.utc),
        confidence=0.4,                              # low — honest for an unfitted heuristic
        source=SOURCE,
        meta_context="waking",                       # cognitive_load is a WAKING sub-context (#14)
        fresh_for_seconds=FRESH_SECONDS,
    )
