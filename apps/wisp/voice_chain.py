"""End-to-end Regis voice chain: compose utterance → synthesize → play.

`speak_moment(...)` is the one entry point. Returns a dict with the utterance,
its mode, the active TTS backend, and timings — so callers can log a complete
record of what Regis said and how long the pipeline took.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Sequence

# apps/inference/ on sys.path for db / llm / embeddings / audio
INFERENCE_DIR = Path(__file__).resolve().parent.parent / "inference"
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from audio import (  # noqa: E402
    MODE_COMPANION,
    MODE_WITNESS,
    get_active_backend,
    play,
    synthesize,
)

from wisp.composer import compose_utterance, _mode_for_kind  # noqa: E402


def speak_moment(
    *,
    user_id: str,
    moment_kind: str,
    explicit_context: str = "",
    retrieval_query: str | None = None,
    retrieval_source_types: Sequence[str] | None = ("dream_recall", "intent"),
    voice: str | None = None,
    speed: float | None = None,
    dry_run: bool = False,
    persist: bool = False,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Compose a Regis utterance and speak it aloud.

    Returns a dict with: text, mode, backend, composition_seconds,
    synthesis_seconds, playback_seconds (0 if dry_run), regis_moment_id (if
    persist=True), audio_bytes (raw WAV — useful for tests / saving).
    """
    composed = compose_utterance(
        user_id=user_id,
        moment_kind=moment_kind,
        explicit_context=explicit_context,
        retrieval_query=retrieval_query,
        retrieval_source_types=retrieval_source_types,
        persist=persist,
        session_id=session_id,
    )

    mode = composed.mode
    backend = get_active_backend()

    t0 = time.monotonic()
    audio_bytes = synthesize(composed.text, mode=mode, voice=voice, speed=speed)
    synthesis_seconds = time.monotonic() - t0

    playback_seconds = 0.0
    if not dry_run:
        t1 = time.monotonic()
        play(audio_bytes)
        playback_seconds = time.monotonic() - t1

    return {
        "text": composed.text,
        "mode": mode,
        "backend": backend,
        "composition_seconds": composed.composition_seconds,
        "synthesis_seconds": synthesis_seconds,
        "playback_seconds": playback_seconds,
        "regis_moment_id": composed.persisted_moment_id,
        "audio_bytes": audio_bytes,
    }


__all__ = ["speak_moment", "MODE_WITNESS", "MODE_COMPANION", "_mode_for_kind"]
