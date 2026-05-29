# apps/inference/features/participant.py
"""L2 Features bus participant — SignalPacket -> FeatureSnapshot.

Subscribes TOPIC_SIGNAL, runs a per-modality extractor, and publishes a
FeaturePacket (FeatureSnapshot) on TOPIC_FEATURE. The extractor registry is the
plug-in seam: real heartpy / librosa / YOLO extractors register here later; the
skeleton ships a passthrough stub that wraps the signal payload into a feature
dict, plus an OFFLINE sentinel for when a modality has no usable extraction.
"""
from __future__ import annotations

from typing import Callable

from core.bus.bus import TOPIC_FEATURE, TOPIC_SIGNAL, MessageBus
from core.layer import forward_envelope
from core.nodes import role_for
from core.protocol.enums import Intent, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import SignalPacket
from features.audio_social import extract as _extract_audio_social
from features.bci import extract as _extract_bci
from features.biometric import extract as _extract_biometric
from features.snapshot import FeatureSnapshot

_COMPONENT = "L2.features"

# Sentinel feature key set on snapshots when no real extraction was possible.
OFFLINE_FEATURE = "__offline__"

# Valid communication-intent values, sourced from the enum (single source of truth).
_INTENT_VALUES = {i.value for i in Intent}
_DEFAULT_INTENT = Intent.CONTINUOUS.value

Extractor = Callable[[SignalPacket], FeatureSnapshot]


def _stub_passthrough_extractor(sig: SignalPacket) -> FeatureSnapshot:
    """Default extractor: wrap the signal payload as features, no transform.

    The clear hook for real per-modality extractors (heartpy for biometric,
    librosa for audio, etc.): register a replacement on the same modality key.
    """
    return FeatureSnapshot(
        user_id=sig.user_id,
        timestamp=sig.timestamp,
        modality=sig.modality,
        source=sig.source,
        payload={"kind": sig.kind, "features": dict(sig.payload), "extractor": "stub_passthrough"},
        intent=sig.intent if sig.intent in _INTENT_VALUES else _DEFAULT_INTENT,
        confidence=sig.confidence,
        i_model_id=sig.i_model_id,
    )


def _offline_extractor(sig: SignalPacket) -> FeatureSnapshot:
    """Degraded sentinel: a well-formed FeatureSnapshot carrying no features."""
    return FeatureSnapshot(
        user_id=sig.user_id,
        timestamp=sig.timestamp,
        modality=sig.modality,
        source=sig.source,
        payload={"kind": sig.kind, OFFLINE_FEATURE: True, "extractor": "offline"},
        intent=sig.intent if sig.intent in _INTENT_VALUES else _DEFAULT_INTENT,
        confidence=None,
        i_model_id=sig.i_model_id,
    )


# Per-modality extractor registry. Keys are Modality values; the skeleton points
# every live modality at the passthrough stub so the pipeline runs end-to-end.
EXTRACTORS: dict[str, Extractor] = {
    "biometric": _extract_biometric,
    "audio": _extract_audio_social,
    "voice": _stub_passthrough_extractor,
    "text": _stub_passthrough_extractor,
    "gesture": _stub_passthrough_extractor,
    "vision": _stub_passthrough_extractor,
    "bci": _extract_bci,
}


def select_extractor(modality: str) -> Extractor:
    """Pick the extractor for a modality; OFFLINE sentinel when unregistered."""
    return EXTRACTORS.get(modality, _offline_extractor)


def extract(sig: SignalPacket) -> FeatureSnapshot:
    """Run the selected extractor over one SignalPacket."""
    return select_extractor(sig.modality)(sig)


def register(bus: MessageBus) -> None:
    """Subscribe the L2 handler to TOPIC_SIGNAL; publish FeaturePackets on TOPIC_FEATURE."""

    def _handle(inbound: MessageEnvelope) -> None:
        if not isinstance(inbound.payload, SignalPacket):
            return
        snapshot = extract(inbound.payload)
        outbound = forward_envelope(
            inbound,
            ptype=PayloadType.FEATURE,
            payload=snapshot,
            source_role=role_for(_COMPONENT),
        )
        bus.publish(TOPIC_FEATURE, outbound)

    bus.subscribe(TOPIC_SIGNAL, _handle)
