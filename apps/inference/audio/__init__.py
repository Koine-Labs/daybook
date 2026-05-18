"""Audio I/O for Daybook.

Two surfaces:
  - synthesize(text, voice=..., speed=..., mode=...) -> bytes      (TTS, returns WAV bytes)
  - play(audio_bytes_or_path) -> None                              (output to default device)
  - speak(text, **kwargs) -> None                                  (one-shot: synth + play)

Default TTS backend: Kokoro (local, 1024-dim, MPS/CUDA/CPU). Fallback: macOS `say` command.
Pick at module init via env var DAYBOOK_TTS=kokoro|say|none (default kokoro).
"""
from __future__ import annotations

from .player import play, AudioPlaybackError
from .streaming import (
    speak_streaming,
    speak_streaming_async,
    is_speaking,
    stop_speaking,
)
from .tts_router import (
    synthesize,
    speak,
    get_active_backend,
    MODE_WITNESS,
    MODE_COMPANION,
    TTSBackendUnavailableError,
)

__all__ = [
    "play",
    "synthesize",
    "speak",
    "speak_streaming",
    "speak_streaming_async",
    "is_speaking",
    "stop_speaking",
    "get_active_backend",
    "MODE_WITNESS",
    "MODE_COMPANION",
    "AudioPlaybackError",
    "TTSBackendUnavailableError",
]
