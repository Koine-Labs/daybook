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


def _social_writer(*, user_id, recorded_at, speaker, num_speakers, vad_active):
    from audio_context.writer import write_social_context
    return write_social_context(user_id, recorded_at, speaker=speaker,
                                num_speakers=num_speakers, vad_active=vad_active)


def _prosody_writer(*, user_id, recorded_at, prosody):
    from audio_context.writer import write_prosody
    return write_prosody(user_id, recorded_at, prosody)


def _ambient_writer(*, user_id, recorded_at, top_classes):
    from audio_context.writer import write_ambient
    return write_ambient(user_id, recorded_at, top_classes)


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


def listen_continuous(
    *,
    user_id: str = DEFAULT_USER_ID,
    wake_word: str | None = None,
    sample_rate: int = 16000,
    block_seconds: float = 0.08,
    window_seconds: float = 3.0,
) -> None:
    """ONE always-on mic loop: wake-word + continuous privacy-gated semantics."""
    import os

    import numpy as np
    import sounddevice as sd

    from audio_context import speaker_id
    from audio_context.ambient import classify_ambient
    from audio_context.diarization import diarize
    from audio_context.prosody import extract_prosody
    from audio_context.vad import detect_voice_activity
    from voice.continuous import ContinuousProcessor
    from wake_word import VoiceWakeWordDetector

    centroid = speaker_id.load_centroid(user_id)

    def identify_speakers(audio, sr):
        segs = diarize(audio, sr)
        ids = set()
        for s in segs:
            i0 = int(s["start_seconds"] * sr); i1 = int(s["end_seconds"] * sr)
            emb = speaker_id.embed_utterance(audio[i0:i1], sr)
            ids.add("unknown" if emb is None else speaker_id.identify(emb, centroid=centroid))
        return sorted(ids)

    proc = ContinuousProcessor(
        user_id=user_id,
        identify_speakers=identify_speakers,
        prosody_of=lambda a, sr: extract_prosody(a, sr).to_dict(),
        ambient_of=lambda a, sr: classify_ambient(a, sr),
        write_social=_social_writer,
        write_prosody=_prosody_writer,
        write_ambient=_ambient_writer,
    )

    ww = wake_word or os.environ.get("DAYBOOK_WAKE_WORD", "hey_jarvis")
    detector = VoiceWakeWordDetector(wake_word=ww, sample_rate=sample_rate)
    block_frames = int(sample_rate * block_seconds)
    window_frames = int(sample_rate * window_seconds)
    buf: list[np.ndarray] = []

    from datetime import datetime, timezone
    print(f"Always-on: wake-word {ww!r} + continuous semantics. Ctrl-C to stop.", flush=True)
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32",
                        blocksize=block_frames) as stream:
        while True:
            audio, _ = stream.read(block_frames)
            chunk = np.asarray(audio[:, 0], dtype=np.float32)

            event = detector.process_audio_chunk(chunk, sample_rate=sample_rate)
            if event is not None:
                detector.reset()
                run_turn(user_id=user_id)
                buf.clear()
                continue

            buf.append(chunk)
            if sum(c.size for c in buf) >= window_frames:
                window = np.concatenate(buf); buf.clear()
                vad_active = len(detect_voice_activity(window, sample_rate)) > 0
                proc.process_window(window, sample_rate, vad_active=vad_active,
                                    now=datetime.now(timezone.utc))
