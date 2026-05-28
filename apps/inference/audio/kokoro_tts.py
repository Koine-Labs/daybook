"""Kokoro TTS via kokoro-onnx — local, fast, no API calls.

Models live at $DAYBOOK_KOKORO_DIR (default ~/.cache/daybook/kokoro/):
    kokoro-v1.0.fp16.onnx  (~170 MB)
    voices-v1.0.bin        (~27 MB)

Download from:
    https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0
"""
from __future__ import annotations

import io
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf


DEFAULT_VOICE = "am_michael"
DEFAULT_SAMPLE_RATE = 24000


class KokoroUnavailable(RuntimeError):
    """Raised when Kokoro cannot be initialized (missing model, import error)."""


def _model_dir() -> Path:
    override = os.environ.get("DAYBOOK_KOKORO_DIR")
    return Path(override) if override else Path.home() / ".cache" / "daybook" / "kokoro"


def _model_paths() -> tuple[Path, Path]:
    d = _model_dir()
    return d / "kokoro-v1.0.fp16.onnx", d / "voices-v1.0.bin"


def is_available() -> bool:
    """Cheap check: kokoro_onnx importable and model files on disk."""
    try:
        import kokoro_onnx  # noqa: F401
    except ImportError:
        return False
    mp, vp = _model_paths()
    return mp.exists() and vp.exists()


@lru_cache(maxsize=1)
def _get_kokoro():
    """Lazily construct and cache the Kokoro instance (single load per process)."""
    try:
        from kokoro_onnx import Kokoro
    except ImportError as exc:
        raise KokoroUnavailable(f"kokoro-onnx not installed: {exc}") from exc

    model_path, voices_path = _model_paths()
    missing = [p for p in (model_path, voices_path) if not p.exists()]
    if missing:
        raise KokoroUnavailable(
            f"Kokoro model files missing: {[str(p) for p in missing]}. "
            "Download from https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0"
        )
    return Kokoro(str(model_path), str(voices_path))


def synthesize_kokoro(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
    lang: str = "en-us",
) -> bytes:
    """Synthesize speech with Kokoro. Returns WAV bytes (16-bit PCM, 24kHz)."""
    if not text or not text.strip():
        raise ValueError("synthesize_kokoro: text is empty")
    kokoro = _get_kokoro()
    audio, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang=lang)
    return _to_wav_bytes(audio, sample_rate)


def _to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    """Encode a float32 mono numpy array as PCM_16 WAV bytes."""
    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def list_voices() -> list[str]:
    """All voice IDs the cached Kokoro instance can produce."""
    return list(_get_kokoro().get_voices())
