"""Full BCI lane arc — synthetic EEG -> L1 -> L2 -> L3 cognitive_load belief.

The headline integration test, mirroring
fusion/test_participant.py::test_live_audio_packet_fuses_social_belief_no_db:
DEFAULT registry, NO DB, NO network, NO hardware. Raw EEG is computed+discarded
at L1; only the eeg_bandpower semantic packet rides the bus (#11).
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.bus.bus import TOPIC_BELIEF, MessageBus
from core.protocol.enums import MetaContext
from core.protocol.envelope import MessageEnvelope
from fusion import participant as fusion_participant
from fusion.belief_state import BeliefState
from features import participant as features_participant
from sensors.eeg_adapter import EEGBusSink, synthesize_eeg_window

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _run_window(band_mix: dict, *, seed: int = 0) -> tuple[list[MessageEnvelope], datetime]:
    now = datetime.now(timezone.utc)
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_BELIEF, captured.append)

    features_participant.register(bus)          # L2: real EXTRACTORS incl. bci.extract
    fusion_participant.register(bus)            # L3: real AXIS_REGISTRY incl. cognitive_load
    sink = EEGBusSink(bus, meta_context=MetaContext.WAKING)  # L1

    samples = synthesize_eeg_window(band_mix=band_mix, noise_uv=1.0, seed=seed)
    sink.write_window(user_id=USER, recorded_at=now, samples=samples)  # raw computed+discarded at L1
    return captured, now


def test_focused_eeg_yields_cognitive_load_belief_no_db():
    captured, now = _run_window({"beta": 25.0}, seed=0)
    assert captured, "no belief published"
    belief = captured[-1].payload
    assert isinstance(belief, BeliefState)

    est = belief.get("cognitive_load", now=now)
    assert est is not None
    assert 0.0 <= est.value["load"] <= 1.0
    assert est.value["band"] in {"low", "medium", "high"}
    assert est.value["scaffold"] is True
    assert est.source.endswith("v1_heuristic")
    assert est.meta_context == "waking"

    # Self-sufficient differential: a focused (beta-heavy) window must yield a
    # strictly higher load than a drowsy (theta-heavy) one, so this marquee arc test
    # alone catches an axis-returns-a-constant mutation (not just the band membership).
    drowsy, dn = _run_window({"theta": 25.0}, seed=0)
    drowsy_load = drowsy[-1].payload.get("cognitive_load", now=dn).value["load"]
    assert est.value["load"] > drowsy_load

    # DB-backed axes degrade to OFFLINE for an EEG packet (no DB touched).
    assert belief.get("meta_context", now=now) is None
    assert belief.get("sleep_stage", now=now) is None
    assert belief.get("audio_social_context", now=now) is None

    # Trace preserved end-to-end; envelope serializes (NetworkTransport-safe).
    assert captured[-1].to_dict()


def test_drowsy_eeg_trends_lower_load_than_focused():
    focused, fn = _run_window({"beta": 25.0}, seed=3)
    drowsy, dn = _run_window({"theta": 25.0}, seed=3)
    f_load = focused[-1].payload.get("cognitive_load", now=fn).value["load"]
    d_load = drowsy[-1].payload.get("cognitive_load", now=dn).value["load"]
    assert d_load < f_load
    assert drowsy[-1].payload.get("cognitive_load", now=dn).value["band"] == "low"


def test_no_raw_samples_ride_the_bus():
    captured, now = _run_window({"alpha": 25.0}, seed=0)
    # The belief envelope's whole serialization must contain no raw sample arrays.
    import json
    blob = json.dumps(captured[-1].to_dict(), default=str)
    assert '"samples"' not in blob
    assert '"raw"' not in blob
