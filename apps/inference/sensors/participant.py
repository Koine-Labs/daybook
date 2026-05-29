"""L1 bus participant: emit SignalPacket envelopes onto TOPIC_SIGNAL.

L1 is the nervous system's entry point — no input topic, so there is no inbound
envelope to inherit from. `emit` builds the envelope directly: fresh trace_id,
a meta_context hint (UNKNOWN by default; L2+ refine it, #14), and a consent_scope
chosen per-modality (#11) from the existing CONSENT_SCOPES registry.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from consent import CONSENT_SCOPES
from core.bus.bus import TOPIC_SIGNAL, MessageBus
from core.protocol.enums import MetaContext, Modality, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import SignalPacket
from sensors.contract import IntentTaggedReading

L1_ROLE = NodeRole.WISP_EDGE

# Map a Modality to its opt-in consent scope; unmapped modalities get this sentinel.
DEFAULT_CONSENT_SCOPE = "unscoped_v0"
_MODALITY_CONSENT: dict[str, str] = {
    Modality.VOICE.value: CONSENT_SCOPES["voice"],
    Modality.AUDIO.value: CONSENT_SCOPES["voice"],
    Modality.BIOMETRIC.value: CONSENT_SCOPES["hk"],
    Modality.BCI.value: CONSENT_SCOPES["eeg"],
    Modality.VISION.value: CONSENT_SCOPES["vision"],
}


def consent_scope_for(reading: IntentTaggedReading) -> str:
    """Pick the consent scope a reading rides under (#11). mac.* sources -> mac scope."""
    if reading.source.startswith("mac."):
        return CONSENT_SCOPES["mac"]
    return _MODALITY_CONSENT.get(reading.modality, DEFAULT_CONSENT_SCOPE)


def build_signal_envelope(
    reading: IntentTaggedReading,
    *,
    meta_context: MetaContext = MetaContext.UNKNOWN,
) -> MessageEnvelope:
    """Wrap a reading's SignalPacket in a fresh L1 envelope (no inbound to inherit)."""
    packet: SignalPacket = reading.to_signal_packet()
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.SIGNAL,
        source_role=L1_ROLE,
        occurred_at=datetime.now(timezone.utc),
        meta_context=meta_context,
        consent_scope=consent_scope_for(reading),
        trace_id=str(uuid.uuid4()),
        payload=packet,
        i_model_id=reading.i_model_id,
    )


def emit(
    bus: MessageBus,
    reading: IntentTaggedReading,
    *,
    meta_context: MetaContext = MetaContext.UNKNOWN,
) -> MessageEnvelope:
    """Publish a reading as a SignalPacket envelope on TOPIC_SIGNAL; return it."""
    env = build_signal_envelope(reading, meta_context=meta_context)
    bus.publish(TOPIC_SIGNAL, env)
    return env
