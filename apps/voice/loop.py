"""Wake-word -> STT -> compose_utterance() -> TTS, with injectable I/O for tests."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

APPS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS_DIR))
sys.path.insert(0, str(APPS_DIR / "inference"))

from wake_word import CommandIntent, classify_intent  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
DEFAULT_MOMENT_KIND = "conversation_tease"


@dataclass
class TurnResult:
    transcript: str
    intent: str
    spoken: bool
    utterance_text: str | None
    mode: str | None


def _default_transcribe() -> str:
    from llm.stt_streaming import transcribe_streaming
    return transcribe_streaming()


def _default_compose(**kwargs: Any):
    from wisp.composer import compose_utterance
    return compose_utterance(**kwargs)


def _default_speak(text: str, *, mode: str) -> None:
    from audio.tts_router import speak
    speak(text, mode=mode)


def run_turn(
    *,
    user_id: str = DEFAULT_USER_ID,
    moment_kind: str = DEFAULT_MOMENT_KIND,
    transcribe: Callable[[], str] = _default_transcribe,
    compose: Callable[..., Any] = _default_compose,
    speak_fn: Callable[..., None] = _default_speak,
) -> TurnResult:
    """One full turn: capture speech, route, compose if it's a message, speak."""
    transcript = (transcribe() or "").strip()
    if not transcript:
        return TurnResult("", CommandIntent.NONE.value, False, None, None)

    intent = classify_intent(transcript)
    if intent in (CommandIntent.DISMISS, CommandIntent.SCRATCH_THAT):
        return TurnResult(transcript, intent.value, False, None, None)

    composed = compose(
        user_id=user_id,
        moment_kind=moment_kind,
        explicit_context=transcript,
        retrieval_query=transcript,
    )
    speak_fn(composed.text, mode=composed.mode)
    return TurnResult(transcript, intent.value, True, composed.text, composed.mode)


def listen_forever(
    *,
    user_id: str = DEFAULT_USER_ID,
    wake_word: str | None = None,
    sample_rate: int = 16000,
    block_seconds: float = 0.08,
) -> None:
    """Block on the mic; on each wake-word, run one turn. Ctrl-C to stop."""
    import os

    import numpy as np
    import sounddevice as sd

    from wake_word import VoiceWakeWordDetector

    ww = wake_word or os.environ.get("DAYBOOK_WAKE_WORD", "hey_jarvis")
    detector = VoiceWakeWordDetector(wake_word=ww, sample_rate=sample_rate)
    block_frames = int(sample_rate * block_seconds)

    print(f"Listening for wake-word {ww!r}. Ctrl-C to stop.", flush=True)
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32",
                        blocksize=block_frames) as stream:
        while True:
            audio, _ = stream.read(block_frames)
            chunk = np.asarray(audio[:, 0], dtype=np.float32)
            event = detector.process_audio_chunk(chunk, sample_rate=sample_rate)
            if event is None:
                continue
            print(f"[wake @ {event.confidence:.2f}] listening...", flush=True)
            detector.reset()
            result = run_turn(user_id=user_id)
            print(f"  -> intent={result.intent} spoken={result.spoken}", flush=True)
