"""L2 BCI extractor — SignalPacket[bci] -> FeatureSnapshot. No DB, no network.

Feeds synthetic eeg_bandpower SignalPackets (built from compute_band_powers on a
known synthetic window) and asserts the structured payload, derived features, and
registry wiring. Mirrors features/biometric's structured payload + EXTRACTOR_TAG.
"""
from __future__ import annotations

from datetime import datetime, timezone

from bci.bandpower import compute_band_powers
from core.protocol.payloads import SignalPacket
from features import bci as bci_extractor
from features import participant as P
from features.snapshot import FeatureSnapshot
from sensors.eeg_adapter import synthesize_eeg_window

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _packet(band_mix: dict, *, seed: int = 0) -> SignalPacket:
    samples = synthesize_eeg_window(band_mix=band_mix, noise_uv=1.0, seed=seed)
    bp = compute_band_powers(samples)
    return SignalPacket(
        user_id=USER,
        timestamp=datetime.now(timezone.utc),
        modality="bci",
        intent="continuous",
        kind="eeg_bandpower",
        payload={
            "absolute": bp["absolute"],
            "relative": bp["relative"],
            "total_power": bp["total_power"],
            "dominant_band": bp["dominant_band"],
        },
        source="eeg_edge_v1",
    )


def test_registry_wires_bci_to_real_extractor():
    assert P.select_extractor("bci") is bci_extractor.extract


def test_extract_produces_structured_snapshot():
    snap = bci_extractor.extract(_packet({"alpha": 25.0}))
    assert isinstance(snap, FeatureSnapshot)
    assert snap.modality == "bci"
    p = snap.payload
    assert p["kind"] == "eeg_bandpower"
    assert p["extractor"] == bci_extractor.EXTRACTOR_TAG
    assert abs(sum(p["bands_relative"].values()) - 1.0) < 1e-6
    feats = p["features"]
    assert feats["engagement_index"] is not None
    assert feats["theta_beta_ratio"] is not None
    assert feats["alpha_power"] is not None


def test_beta_heavy_has_higher_engagement_than_theta_heavy():
    beta = bci_extractor.extract(_packet({"beta": 25.0}, seed=1))
    theta = bci_extractor.extract(_packet({"theta": 25.0}, seed=1))
    assert beta.payload["features"]["engagement_index"] > theta.payload["features"]["engagement_index"]


def test_compute_derived_guards_zero_denominator():
    # Beta == 0 -> theta_beta_ratio denominator is 0 -> None (never inf).
    derived = bci_extractor.compute_derived(
        {"theta": 0.5, "alpha": 0.5, "beta": 0.0, "delta": 0.0, "gamma": 0.0},
        {},
    )
    assert derived["theta_beta_ratio"] is None
    assert derived["engagement_index"] is not None  # alpha+theta > 0


def test_compute_derived_all_zero_yields_none_features():
    derived = bci_extractor.compute_derived({}, {})
    assert derived["engagement_index"] is None
    assert derived["theta_beta_ratio"] is None
    assert derived["alpha_power"] is None


def test_missing_bands_no_crash():
    sig = SignalPacket(
        user_id=USER, timestamp=datetime.now(timezone.utc), modality="bci",
        intent="continuous", kind="eeg_bandpower", payload={}, source="eeg_edge_v1",
    )
    snap = bci_extractor.extract(sig)
    assert snap.payload["features"]["engagement_index"] is None
