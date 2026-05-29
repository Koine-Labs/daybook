"""L1 EEG producer + synthetic generator — no DB, no network, no hardware.

The synthetic raw EEG exists only inside the producer/test boundary; it is
consumed by compute_band_powers and discarded — it never becomes a payload
(semantic-first, #11). Tests assert no raw samples ride the bus and the consent
fix is proven through the real sensors.participant.emit path.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from bci.bandpower import compute_band_powers
from core.bus.bus import TOPIC_SIGNAL, MessageBus
from core.protocol.enums import MetaContext
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import SignalPacket
from sensors.contract import DEFAULT_USER_ID
from sensors.eeg_adapter import EEGBusSink, synthesize_eeg_window

USER = DEFAULT_USER_ID


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_synthesize_returns_finite_1d_window_of_expected_length():
    w = synthesize_eeg_window(fs=256.0, seconds=2.0, seed=0)
    assert w.ndim == 1
    assert w.size == 512
    assert np.all(np.isfinite(w))


def test_synthesize_alpha_mix_round_trips_to_alpha_dominant():
    w = synthesize_eeg_window(band_mix={"alpha": 30.0}, noise_uv=1.0, seed=0)
    bp = compute_band_powers(w)
    assert bp["dominant_band"] == "alpha"


def test_synthesize_default_is_alpha_dominant():
    w = synthesize_eeg_window(seed=1)
    bp = compute_band_powers(w)
    assert bp["dominant_band"] == "alpha"


def _capture_one(sink_fn) -> SignalPacket:
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_SIGNAL, captured.append)
    sink_fn(bus, captured)
    assert len(captured) == 1
    env = captured[0]
    assert isinstance(env.payload, SignalPacket)
    return env


def test_write_window_emits_semantic_packet_no_raw():
    def run(bus, captured):
        sink = EEGBusSink(bus, meta_context=MetaContext.WAKING)
        samples = synthesize_eeg_window(band_mix={"alpha": 30.0}, seed=0)
        sink.write_window(user_id=USER, recorded_at=_now(), samples=samples)

    env = _capture_one(run)
    pkt = env.payload
    assert pkt.modality == "bci"
    assert pkt.intent == "continuous"
    assert pkt.kind == "eeg_bandpower"
    assert "relative" in pkt.payload
    assert "absolute" in pkt.payload
    assert "dominant_band" in pkt.payload
    # Semantic-first: no raw samples ride the bus.
    assert "samples" not in pkt.payload
    assert "raw" not in pkt.payload
    assert all(not isinstance(v, (list, np.ndarray)) for v in (pkt.payload.get("samples"),) if v is not None)


def test_write_window_rides_under_eeg_consent_scope():
    def run(bus, captured):
        sink = EEGBusSink(bus)
        samples = synthesize_eeg_window(seed=0)
        sink.write_window(user_id=USER, recorded_at=_now(), samples=samples)

    env = _capture_one(run)
    assert env.consent_scope == "eeg_continuous_v1"
    assert env.consent_scope != "unscoped_v0"


def test_emit_band_powers_produces_identical_shape():
    samples = synthesize_eeg_window(band_mix={"alpha": 30.0}, seed=0)
    bp = compute_band_powers(samples)

    def run(bus, captured):
        sink = EEGBusSink(bus)
        sink.emit_band_powers(user_id=USER, recorded_at=_now(), band_powers=bp)

    env = _capture_one(run)
    pkt = env.payload
    assert pkt.kind == "eeg_bandpower"
    assert pkt.modality == "bci"
    assert set(pkt.payload["relative"]) == {"delta", "theta", "alpha", "beta", "gamma"}
    assert "samples" not in pkt.payload
    assert pkt.payload["bandpower_version"] == "bandpower.v1"
    assert pkt.payload["channel"] == "single"


def test_bci_reading_consent_scope_is_eeg_not_unscoped():
    from sensors.contract import IntentTaggedReading
    from sensors.participant import consent_scope_for

    reading = IntentTaggedReading(
        modality="bci", intent="continuous", kind="eeg_bandpower",
        payload={"relative": {}}, source="eeg_edge_v1", timestamp=_now(), user_id=USER,
    )
    assert consent_scope_for(reading) == "eeg_continuous_v1"
    assert consent_scope_for(reading) != "unscoped_v0"


def test_write_window_and_emit_band_powers_match():
    samples = synthesize_eeg_window(band_mix={"beta": 25.0}, seed=2)
    bp = compute_band_powers(samples)
    now = _now()

    bus1 = MessageBus(); c1: list[MessageEnvelope] = []
    bus1.subscribe(TOPIC_SIGNAL, c1.append)
    EEGBusSink(bus1).write_window(user_id=USER, recorded_at=now, samples=samples)

    bus2 = MessageBus(); c2: list[MessageEnvelope] = []
    bus2.subscribe(TOPIC_SIGNAL, c2.append)
    EEGBusSink(bus2).emit_band_powers(user_id=USER, recorded_at=now, band_powers=bp)

    assert c1[0].payload.payload == c2[0].payload.payload
