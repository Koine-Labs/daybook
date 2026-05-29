"""L2 BCI feature extractor — eeg_bandpower SignalPacket -> FeatureSnapshot.

Registered for Modality.BCI in features/participant (replacing the passthrough
stub). Mirrors features/biometric.py: a structured payload + EXTRACTOR_TAG that
reuses canonical math. The band-power dict is already computed at L1 (semantic-
first, #11 — the raw EEG was discarded at the edge), so L2 derives the higher-
order, L3-consumable features (theta/beta ratio, alpha power, engagement index).

`compute_derived` is the single source of truth for those derived features (the
analog of audio_social.social_category) and is what the L3 cognitive_load axis
reads — the axis does NOT re-derive from raw bands.
"""
from __future__ import annotations

from typing import Any

from core.protocol.enums import Intent
from core.protocol.payloads import SignalPacket
from features.snapshot import FeatureSnapshot

EXTRACTOR_TAG = "bci_bandpower_features.v1"
_INTENT_VALUES = {i.value for i in Intent}
_DEFAULT_INTENT = Intent.CONTINUOUS.value

_EPS = 1e-9


def _ratio(num: float | None, den: float | None) -> float | None:
    """Guarded division: denominator <= eps -> None (honest, never inf)."""
    if num is None or den is None:
        return None
    if den <= _EPS:
        return None
    return num / den


def compute_derived(relative: dict[str, Any], absolute: dict[str, Any]) -> dict[str, float | None]:
    """Derive the L3-consumable features from RELATIVE band power (scale-invariant).

    All from relative power (robust to single-channel gain drift). Division guards
    return None on a <= eps denominator rather than inf.
    """
    theta = relative.get("theta")
    alpha = relative.get("alpha")
    beta = relative.get("beta")

    theta_beta_ratio = _ratio(theta, beta)
    alpha_theta = (alpha + theta) if (alpha is not None and theta is not None) else None
    engagement_index = _ratio(beta, alpha_theta)

    return {
        "theta_beta_ratio": theta_beta_ratio,  # high -> drowsy / low engagement
        "alpha_power": alpha,                   # relaxed-but-awake; high -> idling cortex
        "engagement_index": engagement_index,   # Pope index; high -> high engagement / load
        "beta_rel": beta,                        # passthrough convenience for the axis
    }


def extract(sig: SignalPacket) -> FeatureSnapshot:
    """eeg_bandpower SignalPacket -> FeatureSnapshot with bands + derived features."""
    p = dict(sig.payload)
    relative = p.get("relative", {}) or {}
    absolute = p.get("absolute", {}) or {}
    derived = compute_derived(relative, absolute)
    return FeatureSnapshot(
        user_id=sig.user_id,
        timestamp=sig.timestamp,
        modality=sig.modality,
        source=sig.source,
        payload={
            "kind": sig.kind,
            "extractor": EXTRACTOR_TAG,
            "bands_relative": relative,
            "bands_absolute": absolute,
            "dominant_band": p.get("dominant_band"),
            "features": derived,
        },
        intent=sig.intent if sig.intent in _INTENT_VALUES else _DEFAULT_INTENT,
        confidence=sig.confidence,
        i_model_id=sig.i_model_id,
    )
