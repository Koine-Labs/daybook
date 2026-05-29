"""L3 axis: affect_prosody — prosody energy/pitch_std -> a [0,1] arousal proxy.

v1 heuristic scaffold (prosodic-arousal linear map). NOT a trained model and NOT
valence: prosody.py::_classify_tone puts `warm` and `raised` both at high energy,
so joy and rage are indistinguishable here. This axis is HONESTLY an arousal proxy
(value carries proxy="prosodic_arousal", valence_discriminating=False), never a
valence number. It exists to drain a currently-wasted real prosody stream (rides
TOPIC_FEATURE with payload kind="audio_prosody" but had zero L3 subscribers) into
the per-axis belief log and the JEPA-era data flywheel (commitment #16); a
stand-alone per-axis scaffold per ARCHITECTURE §2.16's v1 plan, designed to
compose forward, not be thrown away.

True (sign-discriminating) valence is DEFERRED until one of: a facial-affect
extractor lands in the vision lane (SCENE_KEYS has no face/expression field
today), a waking-biometric L3 HRV path exists (HRV is currently SLEEP-locked to
the L4 REM predictor), or prosody gets a trained valence model — documented
exactly as cognitive_load/visual_context document their deferred fuse_recent
paths. Until then, any downstream consumer must honor valence_discriminating=False.

affect_prosody is a WAKING phenomenon in practice and tags meta_context="waking"
like cognitive_load/visual_context — a by-construction tag, NOT a firing gate
(#14's per-context suppression defers to L5/L6 channel selection). Live-only:
there is no audio_prosody sensor-table persistence path, so there is intentionally
NO DB fuse_recent fallback. Pure, DB-free.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from ..belief_state import AxisEstimate

AXIS = "affect_prosody"
SOURCE = "L3.fusion.affect_prosody.v1_heuristic"
FRESH_SECONDS = 120  # prosody shifts fast like cognitive_load; chosen over the audio family's 300s
KIND = "audio_prosody"


def _num(value) -> float | None:
    """NaN-safe scalar read: None if missing or NaN (symmetry with arousal_inferred)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _band(arousal: float) -> str:
    return "low" if arousal < 0.34 else ("medium" if arousal < 0.67 else "high")


def fuse_from_feature(packet, *, now: datetime | None = None) -> AxisEstimate | None:
    """Build a live affect_prosody estimate from an L2 audio FeatureSnapshot, else None.

    Only fires for our own kind (audio_prosody); other kinds/modalities return None
    so the participant records affect_prosody as OFFLINE. Empty/missing prosody (no
    `energy`) also returns None -> OFFLINE. No DB.

    The value is an AROUSAL PROXY (proxy="prosodic_arousal",
    valence_discriminating=False), never valence — energy/pitch_std are activation,
    and _classify_tone collapses joy/rage at high energy. True valence is deferred
    (see module docstring). This axis does NOT gate on meta-context; #14's
    per-context suppression defers to a downstream layer (L5/L6 channel selection).
    """
    feats = getattr(packet, "payload", {}) or {}
    if feats.get("kind") != KIND:
        return None
    p = feats.get("prosody", {}) or {}
    energy = _num(p.get("energy"))
    if energy is None:  # no usable prosody signal (missing or NaN) -> OFFLINE upstream
        return None
    pitch_std = _num(p.get("pitch_std_hz")) or 0.0
    proxy_arousal = max(0.0, min(1.0, 0.6 * energy + 0.4 * min(pitch_std / 60.0, 1.0)))
    return AxisEstimate(
        axis=AXIS,
        value={
            "proxy_arousal": round(proxy_arousal, 3),    # [0,1] scalar — ACTIVATION, not valence
            "band": _band(proxy_arousal),                # "low" | "medium" | "high"
            "tone": p.get("tone"),                       # carried through unchanged
            "energy": energy,
            "pitch_std_hz": p.get("pitch_std_hz"),
            "proxy": "prosodic_arousal",                 # honest: an arousal proxy
            "valence_discriminating": False,             # explicit: NOT a valence number
            "method": "prosody_arousal_map_v1",
            "scaffold": True,                            # explicit: not a trained model
        },
        timestamp=getattr(packet, "timestamp", None) or now or datetime.now(timezone.utc),
        confidence=0.3,                                  # lower than cognitive_load — weaker, sign-unstable proxy
        source=SOURCE,
        meta_context="waking",                           # by-construction tag, NOT a firing gate (#14)
        fresh_for_seconds=FRESH_SECONDS,
    )
