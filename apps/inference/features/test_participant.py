"""Smoke test for the L2 Features bus participant."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.bus.bus import TOPIC_FEATURE, TOPIC_SIGNAL, MessageBus
from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import SignalPacket
from features.participant import OFFLINE_FEATURE, register
from features.snapshot import FeatureSnapshot


# Default modality is 'text' (still backed by the passthrough stub). Biometric
# now routes to the real feature extractor (features/biometric.py), whose
# behavior is exercised in test_biometric.py; this file tests the participant's
# generic passthrough + envelope-inheritance contract.
def _signal_env(modality: str = "text", *, kind: str = "hr_30s",
                payload: dict | None = None) -> MessageEnvelope:
    sig = SignalPacket(
        user_id="61c18d4c-1c20-408a-bd5f-f5f88fd9922f",
        timestamp=datetime(2026, 5, 27, 15, 0, tzinfo=timezone.utc),
        modality=modality,
        intent="continuous",
        kind=kind,
        payload=payload if payload is not None else {"hr_mean": 68.2, "hr_std": 3.1},
        source="watch.hr_30s",
        confidence=0.8,
        i_model_id="im-1",
    )
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.SIGNAL,
        source_role=NodeRole.WISP_EDGE,
        occurred_at=datetime.now(timezone.utc),
        meta_context=MetaContext.SLEEP,
        consent_scope="sleep_session",
        trace_id="trace-l2",
        payload=sig,
        i_model_id="im-1",
    )


def test_signal_in_feature_out_same_trace():
    bus = MessageBus()
    got: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_FEATURE, got.append)
    register(bus)

    inbound = _signal_env()
    bus.publish(TOPIC_SIGNAL, inbound)

    assert len(got) == 1
    out = got[0]
    assert out.type == PayloadType.FEATURE
    assert out.trace_id == inbound.trace_id
    assert out.meta_context == inbound.meta_context
    assert out.consent_scope == inbound.consent_scope
    assert out.i_model_id == inbound.i_model_id
    assert out.source_role == NodeRole.WISP_EDGE  # L2.features placement
    assert isinstance(out.payload, FeatureSnapshot)
    assert out.payload.modality == "text"
    assert out.payload.payload["features"]["hr_mean"] == 68.2
    assert out.payload.intent == "continuous"
    out.to_dict()  # serializes without raising


def test_unknown_modality_routes_to_offline_sentinel():
    bus = MessageBus()
    got: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_FEATURE, got.append)
    register(bus)

    bus.publish(TOPIC_SIGNAL, _signal_env(modality="lidar", kind="ping", payload={}))

    assert len(got) == 1
    snap = got[0].payload
    assert isinstance(snap, FeatureSnapshot)
    assert snap.payload.get(OFFLINE_FEATURE) is True
    assert snap.confidence is None  # never fabricate confidence when offline


def test_confidence_in_range_preserved():
    bus = MessageBus()
    got: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_FEATURE, got.append)
    register(bus)

    bus.publish(TOPIC_SIGNAL, _signal_env())
    assert got[0].payload.confidence == 0.8
