"""Speech-to-text wrapper for Daybook.

Thin re-export of the local Whisper used by `apps/recall/whisper_client.py`
plus a `record_and_transcribe()` helper that combines `apps/recall/recorder.py`
with whisper in one call. Lets non-recall modules (voice chat, intent, mood)
use the same STT path without duplicating the model load.

Public surface:
  - transcribe(audio_path)              -> str
  - record_and_transcribe(...)          -> RecordedTranscript
  - RecordedTranscript dataclass
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

APPS_DIR = Path(__file__).resolve().parent.parent.parent
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from recall.whisper_client import transcribe as _whisper_transcribe  # noqa: E402

DEFAULT_AUDIO_DIR = Path.home() / ".daybook" / "voice_audio"


@dataclass
class RecordedTranscript:
    """Result of a record-then-transcribe pass."""

    text: str
    audio_path: Path
    recorded_at: datetime
    record_seconds: float
    transcribe_seconds: float


def transcribe(audio_path: str | Path, *, language: str | None = "en") -> str:
    """Transcribe a local audio file (re-exports recall.whisper_client.transcribe)."""
    return _whisper_transcribe(audio_path, language=language)


def record_and_transcribe(
    *,
    max_seconds: int = 30,
    prompt: str = "Speak now... (press ENTER to stop)",
    audio_dir: Path | None = None,
    language: str | None = "en",
    show_progress: bool = True,
) -> RecordedTranscript:
    """Record from default mic until ENTER (or max_seconds), then transcribe."""
    import time

    from recall.recorder import record_interactive

    audio_dir = Path(audio_dir) if audio_dir else DEFAULT_AUDIO_DIR
    audio_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc)
    out_path = audio_dir / f"{started_at.isoformat().replace(':', '-')}.wav"

    if prompt:
        print(prompt)

    rec_t0 = time.monotonic()
    record_interactive(out_path, max_seconds=max_seconds, show_progress=show_progress)
    rec_secs = time.monotonic() - rec_t0

    trans_t0 = time.monotonic()
    text = transcribe(out_path, language=language).strip()
    trans_secs = time.monotonic() - trans_t0

    return RecordedTranscript(
        text=text,
        audio_path=out_path,
        recorded_at=started_at,
        record_seconds=rec_secs,
        transcribe_seconds=trans_secs,
    )


__all__ = ["RecordedTranscript", "transcribe", "record_and_transcribe"]
