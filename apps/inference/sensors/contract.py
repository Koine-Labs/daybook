"""L1 capture contract: a tagged reading and its conversion to a SignalPacket.

`IntentTaggedReading` is the modality + intent envelope (commitment #10) that
every L1 capture source produces, before it rides the bus as a SignalPacket.
Semantic-first (#11): only meaningful extractions, never raw bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.protocol.enums import Intent, Modality
from core.protocol.payloads import SignalPacket

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"

_MODALITY_VALUES = {m.value for m in Modality}
_INTENT_VALUES = {i.value for i in Intent}


@dataclass
class IntentTaggedReading:
    """One L1 capture, tagged by modality + intent (commitment #10)."""

    modality: str                     # a Modality value
    intent: str                       # an Intent value
    kind: str                         # e.g. 'mac_activity', 'hr_30s', 'speech_final'
    payload: dict[str, Any]           # semantic-first extraction (#11)
    source: str                       # e.g. 'mac.app_activity', 'watch.hr_30s'
    timestamp: datetime               # tz-aware UTC
    confidence: float | None = None
    user_id: str = DEFAULT_USER_ID
    i_model_id: str | None = None     # commitment #1

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("IntentTaggedReading.timestamp must be tz-aware UTC")
        if self.modality not in _MODALITY_VALUES:
            raise ValueError(f"unknown modality {self.modality!r}; expected one of {sorted(_MODALITY_VALUES)}")
        if self.intent not in _INTENT_VALUES:
            raise ValueError(f"unknown intent {self.intent!r}; expected one of {sorted(_INTENT_VALUES)}")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")

    def to_signal_packet(self) -> SignalPacket:
        """Convert this reading into the L1->L2 SignalPacket payload."""
        return to_signal_packet(self)


def to_signal_packet(reading: IntentTaggedReading) -> SignalPacket:
    """Free-function form of the reading -> SignalPacket conversion."""
    return SignalPacket(
        user_id=reading.user_id,
        timestamp=reading.timestamp,
        modality=reading.modality,
        intent=reading.intent,
        kind=reading.kind,
        payload=reading.payload,
        source=reading.source,
        confidence=reading.confidence,
        i_model_id=reading.i_model_id,
    )
