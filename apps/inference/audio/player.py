"""Blocking audio playback via sounddevice + soundfile.

Accepts WAV/MP3 bytes (in-memory) or a path (str | Path). Plays through the OS
default output device (Bluetooth if connected, else internal speakers — that's
the OS's call, not ours).
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf


class AudioPlaybackError(RuntimeError):
    """Raised when audio playback fails for any reason."""


def play(audio: bytes | str | Path) -> None:
    """Play audio bytes (WAV/MP3) or a file path. Blocks until done."""
    try:
        data, sample_rate = _decode(audio)
    except Exception as exc:
        raise AudioPlaybackError(f"Failed to decode audio: {exc}") from exc

    try:
        sd.play(data, samplerate=sample_rate, blocking=True)
    except Exception as exc:
        raise AudioPlaybackError(f"sounddevice playback failed: {exc}") from exc


def _decode(audio: bytes | str | Path) -> tuple[np.ndarray, int]:
    """Return (numpy float32 array, sample_rate). Soundfile auto-detects format."""
    if isinstance(audio, (str, Path)):
        path = Path(audio)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")
        data, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
        return data, sample_rate

    if isinstance(audio, (bytes, bytearray, memoryview)):
        with io.BytesIO(bytes(audio)) as buf:
            data, sample_rate = sf.read(buf, dtype="float32", always_2d=False)
        return data, sample_rate

    raise TypeError(f"Unsupported audio input type: {type(audio).__name__}")
