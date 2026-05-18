"""TTS backend router.

Picks the active backend at import time based on availability + env override.
Resolution order: $DAYBOOK_TTS env (if set) → kokoro (if installed + models) → say
(macOS) → none.

Mode constants drive defaults for Regis:
  - witness: slower, softer (sleep — sparse, reverent)
  - companion: normal tempo (awake — dry, teasing)
"""
from __future__ import annotations

import os
from typing import Literal

from . import kokoro_tts, say_tts
from .player import play


MODE_WITNESS = "witness"
MODE_COMPANION = "companion"

Mode = Literal["witness", "companion"]
Backend = Literal["kokoro", "say", "none"]

# Per-mode synthesis defaults. Tuned for Regis's two voices.
_MODE_DEFAULTS_KOKORO: dict[str, dict[str, float | str]] = {
    MODE_WITNESS: {"speed": 0.85, "voice": "am_michael"},
    MODE_COMPANION: {"speed": 1.0, "voice": "am_michael"},
}
_MODE_DEFAULTS_SAY: dict[str, dict[str, int | str]] = {
    MODE_WITNESS: {"rate": 140, "voice": "Daniel"},
    MODE_COMPANION: {"rate": 180, "voice": "Daniel"},
}


class TTSBackendUnavailableError(RuntimeError):
    """Raised by synthesize/speak when no TTS backend is active."""


def _resolve_backend() -> Backend:
    """Decide which backend to use this process. Honor $DAYBOOK_TTS override."""
    forced = os.environ.get("DAYBOOK_TTS", "").strip().lower()
    if forced == "kokoro":
        return "kokoro" if kokoro_tts.is_available() else "none"
    if forced == "say":
        return "say" if say_tts.is_available() else "none"
    if forced == "none":
        return "none"
    if forced and forced not in {"kokoro", "say", "none"}:
        raise ValueError(f"Unknown DAYBOOK_TTS value: {forced!r}")

    if kokoro_tts.is_available():
        return "kokoro"
    if say_tts.is_available():
        return "say"
    return "none"


_ACTIVE_BACKEND: Backend = _resolve_backend()


def get_active_backend() -> Backend:
    """Return current backend tag — for diagnostics + smoke tests."""
    return _ACTIVE_BACKEND


def synthesize(
    text: str,
    *,
    mode: Mode = MODE_COMPANION,
    voice: str | None = None,
    speed: float | None = None,
) -> bytes:
    """Route to the active TTS backend. Returns WAV bytes (PCM_16)."""
    if _ACTIVE_BACKEND == "none":
        raise TTSBackendUnavailableError(
            "No TTS backend active. Install kokoro-onnx + models, or run on macOS for `say` fallback."
        )

    if _ACTIVE_BACKEND == "kokoro":
        defaults = _MODE_DEFAULTS_KOKORO[mode]
        return kokoro_tts.synthesize_kokoro(
            text,
            voice=voice or str(defaults["voice"]),
            speed=speed if speed is not None else float(defaults["speed"]),
        )

    if _ACTIVE_BACKEND == "say":
        defaults = _MODE_DEFAULTS_SAY[mode]
        base_rate = int(defaults["rate"])
        rate = int(base_rate * speed) if speed is not None else base_rate
        return say_tts.synthesize_say(
            text,
            voice=voice or str(defaults["voice"]),
            rate=rate,
        )

    raise TTSBackendUnavailableError(f"Unhandled backend: {_ACTIVE_BACKEND}")


def speak(
    text: str,
    *,
    mode: Mode = MODE_COMPANION,
    voice: str | None = None,
    speed: float | None = None,
) -> None:
    """Synthesize and play immediately. Blocks until playback finishes."""
    wav = synthesize(text, mode=mode, voice=voice, speed=speed)
    play(wav)
