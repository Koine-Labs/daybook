"""Audio context awareness: semantic-first ambient audio understanding.

VAD, speaker diarization, and prosody features extracted from raw audio chunks.
NO transcription here (Agent A owns STT). Outputs semantic packets suitable
for persistence in `sensor_readings` as kind='audio_segment'.

These modules process audio chunks. A future daemon will feed them from a
continuous mic stream.
"""

from __future__ import annotations

from audio_context.processor import (
    AudioContextPacket,
    persist_packet,
    process_audio_chunk,
)
from audio_context.prosody import ProsodyFeatures, extract_prosody
from audio_context.vad import detect_voice_activity, is_speech_now
from audio_context.diarization import diarize

__all__ = [
    "AudioContextPacket",
    "ProsodyFeatures",
    "detect_voice_activity",
    "diarize",
    "extract_prosody",
    "is_speech_now",
    "persist_packet",
    "process_audio_chunk",
]
