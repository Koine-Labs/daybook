"""L1 audio producer: privacy-gated mic semantics -> SignalPacket on the bus.

Wraps voice.continuous.ContinuousProcessor (REUSED — VAD/diarization/prosody/
ambient + the Privacy Policy #1 state machine are not reimplemented here). Each
allowed semantic emission becomes an IntentTaggedReading (modality=AUDIO,
intent=CONTINUOUS, #10) and is published via sensors.participant.emit. Semantic-
first (#11): only derived values ride the bus, never raw audio.

Transport-agnostic: holds only a MessageBus, so it works over InProcessTransport
(mic on the Mac today) and NetworkTransport (mic on the Pi later) with no change.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from core.bus.bus import MessageBus
from core.protocol.enums import Intent, Modality
from sensors.contract import DEFAULT_USER_ID, IntentTaggedReading
from sensors.participant import emit

AUDIO_SOURCE = "mic_listener_v1"          # matches audio_context/writer.SOURCE
KIND_SOCIAL = "audio_social_context"
KIND_PROSODY = "audio_prosody"
KIND_AMBIENT = "audio_ambient"


def _reading(kind: str, payload: dict[str, Any], *, user_id: str, now: datetime) -> IntentTaggedReading:
    return IntentTaggedReading(
        modality=Modality.AUDIO.value,
        intent=Intent.CONTINUOUS.value,
        kind=kind,
        payload=payload,
        source=AUDIO_SOURCE,
        timestamp=now,
        user_id=user_id,
    )


class AudioBusSink:
    """The three writer callables ContinuousProcessor expects, but each emits a
    SignalPacket onto a MessageBus instead of writing the DB."""

    def __init__(self, bus: MessageBus, *, user_id: str = DEFAULT_USER_ID) -> None:
        self.bus = bus
        self.user_id = user_id

    def write_social(self, *, user_id: str, recorded_at: datetime, speaker: str,
                     num_speakers: int, vad_active: bool) -> None:
        emit(self.bus, _reading(KIND_SOCIAL, {
            "speaker": speaker, "num_speakers": num_speakers, "vad_active": vad_active,
        }, user_id=user_id, now=recorded_at))

    def write_prosody(self, *, user_id: str, recorded_at: datetime, prosody: dict[str, Any]) -> None:
        emit(self.bus, _reading(KIND_PROSODY, dict(prosody), user_id=user_id, now=recorded_at))

    def write_ambient(self, *, user_id: str, recorded_at: datetime, top_classes: list) -> None:
        emit(self.bus, _reading(KIND_AMBIENT, {"top_classes": list(top_classes)},
                                user_id=user_id, now=recorded_at))
