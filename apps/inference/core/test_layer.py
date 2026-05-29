from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.layer import forward_envelope
from core.protocol.enums import (Intent, MetaContext, Modality, NodeRole, PayloadType)
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import FeatureSnapshot, SignalPacket

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _inbound() -> MessageEnvelope:
    sig = SignalPacket(user_id=USER, timestamp=datetime.now(timezone.utc),
                       modality=Modality.AUDIO.value, intent=Intent.CONTINUOUS.value,
                       kind="speech_final", payload={"text": "mm"}, source="mac.mic")
    return MessageEnvelope(
        id=str(uuid.uuid4()), type=PayloadType.SIGNAL, source_role=NodeRole.WISP_EDGE,
        occurred_at=datetime.now(timezone.utc), meta_context=MetaContext.SLEEP,
        consent_scope="mic_continuous_v1", trace_id=str(uuid.uuid4()), payload=sig,
        i_model_id="im-abc-123")


def _forward(inbound: MessageEnvelope) -> MessageEnvelope:
    snap = FeatureSnapshot(user_id=inbound.payload.user_id,
                           timestamp=inbound.payload.timestamp,
                           modality=inbound.payload.modality, source=inbound.payload.source,
                           payload={"echo": inbound.payload.payload},
                           intent=inbound.payload.intent)
    return forward_envelope(inbound, ptype=PayloadType.FEATURE, payload=snap,
                            source_role=NodeRole.WISP_EDGE)


def test_fresh_id_distinct_from_inbound():
    inbound = _inbound()
    out = _forward(inbound)
    assert out.id != inbound.id
    uuid.UUID(out.id)  # raises if not a valid uuid


def test_trace_meta_consent_imodel_inherited():
    inbound = _inbound()
    out = _forward(inbound)
    assert out.trace_id == inbound.trace_id
    assert out.meta_context == inbound.meta_context == MetaContext.SLEEP
    assert out.consent_scope == inbound.consent_scope == "mic_continuous_v1"
    assert out.i_model_id == inbound.i_model_id == "im-abc-123"


def test_layer_sets_its_own_type_and_role():
    inbound = _inbound()
    out = forward_envelope(inbound, ptype=PayloadType.FEATURE, payload=_forward(inbound).payload,
                           source_role=NodeRole.DESKTOP_COMPUTE, target_role=NodeRole.CLOUD)
    assert out.type == PayloadType.FEATURE
    assert out.source_role == NodeRole.DESKTOP_COMPUTE
    assert out.target_role == NodeRole.CLOUD


def test_occurred_at_is_tz_aware_utc():
    inbound = _inbound()
    out = _forward(inbound)
    assert out.occurred_at.tzinfo is not None
    assert out.occurred_at.utcoffset() == timezone.utc.utcoffset(None)
