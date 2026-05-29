"""L3 affect_prosody axis unit tests — pure, DB-free.

Mirrors test_cognitive_load.py's fuse_from_feature block. Asserts the prosodic-
arousal proxy responds to energy/pitch_std and carries honest scaffold provenance
(arousal proxy, NOT valence — valence_discriminating is False).
"""
from __future__ import annotations

from datetime import datetime, timezone

from features.snapshot import FeatureSnapshot
from fusion.axes import affect_prosody as ap
from fusion.belief_state import AxisEstimate


def _feature(prosody: dict, *, kind: str = "audio_prosody") -> FeatureSnapshot:
    return FeatureSnapshot(
        user_id="u1",
        timestamp=datetime.now(timezone.utc),
        modality="audio",
        source="audio_prosody_v1",
        payload={"kind": kind, "prosody": prosody},
    )


def test_high_energy_high_pitch_std_yields_high_band():
    now = datetime.now(timezone.utc)
    est = ap.fuse_from_feature(
        _feature({"energy": 0.8, "pitch_std_hz": 50.0, "tone": "raised"}),
        now=now,
    )
    assert isinstance(est, AxisEstimate)
    assert est.axis == "affect_prosody"
    assert 0.0 <= est.value["proxy_arousal"] <= 1.0
    assert est.value["band"] == "high"
    assert est.value["proxy"] == "prosodic_arousal"
    assert est.value["valence_discriminating"] is False
    assert est.value["scaffold"] is True
    assert est.value["method"] == "prosody_arousal_map_v1"
    assert est.confidence == 0.3
    assert est.meta_context == "waking"
    assert est.fresh_for_seconds == 120
    assert est.source.endswith("v1_heuristic")


def test_quiet_low_pitch_std_yields_low_band():
    est = ap.fuse_from_feature(_feature({"energy": 0.05, "pitch_std_hz": 5.0, "tone": "flat"}))
    assert est.value["band"] == "low"


def test_non_prosody_kind_returns_none():
    assert ap.fuse_from_feature(
        _feature({"energy": 0.8, "pitch_std_hz": 50.0}, kind="audio_social_context")
    ) is None


def test_empty_or_missing_prosody_returns_none():
    assert ap.fuse_from_feature(_feature({})) is None
    assert ap.fuse_from_feature(_feature({"pitch_std_hz": 50.0, "tone": "warm"})) is None


def test_tone_label_passes_through_unchanged():
    est = ap.fuse_from_feature(_feature({"energy": 0.5, "pitch_std_hz": 20.0, "tone": "warm"}))
    assert est.value["tone"] == "warm"


def test_band_boundary_low_medium_cut_at_034():
    """Pin the low/medium band cut at 0.34 (kills the 0.34 -> 0.5 mutation).

    energy=0.6, pitch_std=0 yields proxy_arousal 0.36 (just above the cut -> medium);
    energy=0.4, pitch_std=0 yields 0.24 (below -> low).
    """
    at_036 = ap.fuse_from_feature(_feature({"energy": 0.6, "pitch_std_hz": 0.0, "tone": "flat"}))
    assert at_036.value["proxy_arousal"] == 0.36
    assert at_036.value["band"] == "medium"

    at_024 = ap.fuse_from_feature(_feature({"energy": 0.4, "pitch_std_hz": 0.0, "tone": "flat"}))
    assert at_024.value["proxy_arousal"] == 0.24
    assert at_024.value["band"] == "low"


def test_proxy_arousal_exact_value():
    """Pin the 0.6/0.4 energy/pitch coefficients structurally (kills weight drift).

    energy=0.8, pitch_std=30 -> 0.6*0.8 + 0.4*min(30/60,1) = 0.68; any drift in the
    coefficients (e.g. 0.6 -> 0.5) that stays within a band would otherwise survive.
    """
    est = ap.fuse_from_feature(_feature({"energy": 0.8, "pitch_std_hz": 30.0, "tone": "raised"}))
    assert est.value["proxy_arousal"] == round(0.6 * 0.8 + 0.4 * 0.5, 3)


def test_nan_energy_does_not_silently_max_arousal():
    """A NaN energy is unusable signal -> None (OFFLINE), never a fabricated max.

    Without a NaN guard, max(0.0, min(1.0, nan)) == 1.0 in CPython, silently
    reporting MAXIMUM arousal. The honest behavior is the same as missing energy.
    """
    assert ap.fuse_from_feature(_feature({"energy": float("nan"), "pitch_std_hz": 30.0})) is None
