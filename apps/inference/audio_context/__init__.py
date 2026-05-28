"""Audio context awareness: semantic-first ambient audio understanding.

VAD, speaker diarization, and prosody features extracted from raw audio chunks.
NO transcription here. The continuous mic loop (apps/voice/) feeds these from
one always-on stream; persistence is consent-stamped + privacy-gated in
audio_context/writer.py. There is no ungated write path in this package.
"""

from __future__ import annotations

from audio_context.processor import AudioContextPacket, process_audio_chunk
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
    "process_audio_chunk",
]
