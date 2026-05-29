"""L2 audio extractor unit + bus-arc tests — no torch, no DB, no mic."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.bus.bus import TOPIC_FEATURE, TOPIC_SIGNAL, MessageBus
from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import SignalPacket
from features.audio_social import EXTRACTOR_TAG, extract, social_category
from features.participant import register, select_extractor
from features.snapshot import FeatureSnapshot

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _sig(kind: str, payload: dict) -> SignalPacket:
    return SignalPacket(
        user_id=USER,
        timestamp=datetime(2026, 5, 29, 12, 0, tzinfo=timezone.utc),
        modality="audio",
        intent="continuous",
        kind=kind,
        payload=payload,
        source="mic_listener_v1",
        confidence=0.8,
    )


def test_social_context_with_other():
    snap = extract(_sig("audio_social_context",
                        {"speaker": "both", "num_speakers": 2, "vad_active": True}))
    assert isinstance(snap, FeatureSnapshot)
    assert snap.modality == "audio"
    assert snap.payload["extractor"] == EXTRACTOR_TAG
    assert snap.payload["social_category"] == "with_other"
    assert snap.payload["speaker"] == "both"


def test_social_context_alone():
    snap = extract(_sig("audio_social_context", {"speaker": "self", "vad_active": True}))
    assert snap.payload["social_category"] == "alone"
    assert social_category("self") == "alone"
    assert social_category("none") == "alone"


def test_prosody_passthrough():
    prosody = {"energy": 0.5, "pitch_mean_hz": 110.0, "tone": "calm"}
    snap = extract(_sig("audio_prosody", prosody))
    assert snap.payload["prosody"] == prosody


def test_ambient_class_list():
    classes = [{"class": "Silence", "score": 0.9}]
    snap = extract(_sig("audio_ambient", {"top_classes": classes}))
    assert snap.payload["ambient"] == classes


def test_registry_audio_is_real_extractor_voice_is_stub():
    assert select_extractor("audio") is extract
    assert select_extractor("voice") is not extract  # voice stays on the stub


def test_bus_arc_signal_to_feature_same_trace():
    bus = MessageBus()
    got: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_FEATURE, got.append)
    register(bus)

    inbound = MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.SIGNAL,
        source_role=NodeRole.WISP_EDGE,
        occurred_at=datetime.now(timezone.utc),
        meta_context=MetaContext.WAKING,
        consent_scope="mic_continuous_v1",
        trace_id="trace-audio",
        payload=_sig("audio_social_context", {"speaker": "other", "vad_active": True}),
    )
    bus.publish(TOPIC_SIGNAL, inbound)

    assert len(got) == 1
    out = got[0]
    assert out.trace_id == "trace-audio"
    assert isinstance(out.payload, FeatureSnapshot)
    assert out.payload.payload["social_category"] == "with_other"
