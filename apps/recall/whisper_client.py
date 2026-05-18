"""Local Whisper wrapper. Lazy model load, single global instance."""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import whisper as _whisper

logger = logging.getLogger(__name__)

WHISPER_MODEL_TAG = os.environ.get("DAYBOOK_WHISPER_MODEL", "base")


@lru_cache(maxsize=1)
def get_model() -> "_whisper.Whisper":
    """Load Whisper once per process (default: 'base' = 74MB, English-leaning)."""
    import whisper

    logger.info("Loading Whisper model %r ...", WHISPER_MODEL_TAG)
    model = whisper.load_model(WHISPER_MODEL_TAG)
    logger.info("Loaded Whisper %r.", WHISPER_MODEL_TAG)
    return model


def transcribe(audio_path: str | Path, *, language: str | None = "en") -> str:
    """Transcribe a local audio file. Returns stripped text."""
    p = Path(audio_path)
    if not p.exists():
        raise FileNotFoundError(f"Audio file not found: {p}")
    model = get_model()
    result = model.transcribe(
        str(p),
        language=language,
        fp16=False,  # fp16 on CPU produces a warning; explicit off keeps logs clean
    )
    text = (result.get("text") or "").strip()
    return text
