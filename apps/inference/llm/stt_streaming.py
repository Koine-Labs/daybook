"""Streaming speech-to-text via chunked faster-whisper.

Records from the mic in short chunks, transcribes each as it lands, emits a
running partial transcript through a callback. Stops on sustained silence
(simple RMS energy gate) or after max_seconds.

Public surface:
  - transcribe_streaming(...)         -> str
  - transcribe_wav_streaming(path)    -> str    (file-based; for smoke tests)
  - get_streaming_backend()           -> "faster-whisper" | "whisper" | "none"
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000  # whisper-native
CHANNELS = 1

# Chunk length pulled from mic before transcription. Shorter = lower latency,
# more transcription overhead. 1.5s is a reasonable compromise on Apple Silicon.
DEFAULT_CHUNK_SECONDS = 1.5
# RMS below this on a chunk counts as "silent" for VAD purposes. Tuned for
# typical room noise on the MacBook internal mic; override per call if needed.
DEFAULT_SILENCE_RMS = 0.012

_FASTER_WHISPER_MODEL = os.environ.get("DAYBOOK_FASTER_WHISPER_MODEL", "small.en")
_FASTER_WHISPER_COMPUTE = os.environ.get("DAYBOOK_FASTER_WHISPER_COMPUTE", "int8")


def get_streaming_backend() -> str:
    """Return which STT backend will be used. Prefers faster-whisper."""
    try:
        import faster_whisper  # noqa: F401

        return "faster-whisper"
    except ImportError:
        pass
    try:
        import whisper  # noqa: F401

        return "whisper"
    except ImportError:
        return "none"


@lru_cache(maxsize=1)
def _get_faster_whisper_model():
    """Lazy-load the faster-whisper model once per process."""
    from faster_whisper import WhisperModel

    logger.info(
        "Loading faster-whisper model %r (compute=%s)",
        _FASTER_WHISPER_MODEL,
        _FASTER_WHISPER_COMPUTE,
    )
    return WhisperModel(_FASTER_WHISPER_MODEL, compute_type=_FASTER_WHISPER_COMPUTE)


def _transcribe_array_faster_whisper(audio: np.ndarray, *, language: str | None) -> str:
    """faster-whisper path: takes float32 mono audio, returns text.

    vad_filter=True dramatically helps with short utterances by stripping silence
    + low-energy padding before the model sees it. beam_size=5 modestly improves
    accuracy at small latency cost (worth it for conversational use).
    """
    model = _get_faster_whisper_model()
    segments, _info = model.transcribe(
        audio,
        language=language,
        beam_size=5,
        condition_on_previous_text=False,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 250},
    )
    return "".join(seg.text for seg in segments).strip()


def _transcribe_array_whisper(audio: np.ndarray, *, language: str | None) -> str:
    """openai-whisper fallback path. Slower; only used if faster-whisper missing."""
    import sys

    apps_dir = Path(__file__).resolve().parent.parent.parent
    if str(apps_dir) not in sys.path:
        sys.path.insert(0, str(apps_dir))
    from recall.whisper_client import get_model

    model = get_model()
    result = model.transcribe(audio, language=language, fp16=False)
    return (result.get("text") or "").strip()


def _transcribe_chunk(audio: np.ndarray, *, language: str | None) -> str:
    """Route a single chunk to the active backend."""
    backend = get_streaming_backend()
    if backend == "faster-whisper":
        return _transcribe_array_faster_whisper(audio, language=language)
    if backend == "whisper":
        return _transcribe_array_whisper(audio, language=language)
    raise RuntimeError(
        "No streaming STT backend available. Install faster-whisper or openai-whisper."
    )


def _rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


def transcribe_streaming(
    *,
    max_seconds: float = 30.0,
    silence_seconds: float = 1.5,
    chunk_seconds: float = DEFAULT_CHUNK_SECONDS,
    silence_rms: float = DEFAULT_SILENCE_RMS,
    language: str | None = "en",
    on_partial: Callable[[str], None] | None = None,
    on_final: Callable[[str], None] | None = None,
) -> str:
    """Mic-streaming transcription. Returns final transcript.

    Yields partials through `on_partial` as each chunk transcribes; calls
    `on_final` once with the trimmed full transcript before returning.
    """
    import sounddevice as sd

    chunk_frames = int(SAMPLE_RATE * chunk_seconds)
    silence_chunks_needed = max(1, int(round(silence_seconds / chunk_seconds)))

    audio_q: queue.Queue[np.ndarray] = queue.Queue()
    stop_event = threading.Event()
    captured: list[np.ndarray] = []

    def callback(indata, _frames, _time_info, status):
        if status:
            logger.warning("sounddevice status: %s", status)
        # indata is float32 (we'll set dtype below). Copy or it gets reused.
        audio_q.put(indata[:, 0].copy() if indata.ndim > 1 else indata.copy())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=chunk_frames,
        callback=callback,
    )

    partials: list[str] = []
    silent_streak = 0
    started = time.monotonic()

    with stream:
        while not stop_event.is_set():
            if time.monotonic() - started > max_seconds:
                break
            try:
                chunk = audio_q.get(timeout=chunk_seconds + 0.5)
            except queue.Empty:
                continue
            captured.append(chunk)

            energy = _rms(chunk)
            if energy < silence_rms:
                silent_streak += 1
            else:
                silent_streak = 0

            # Only transcribe non-silent chunks (cuts wasted compute on silence).
            if energy >= silence_rms:
                text = _transcribe_chunk(chunk, language=language)
                if text:
                    partials.append(text)
                    if on_partial:
                        on_partial(" ".join(partials))

            if silent_streak >= silence_chunks_needed and captured:
                # Only stop on silence after we've actually heard speech.
                if any(p for p in partials):
                    break

    # Final pass: concatenate everything and re-transcribe for coherence.
    if captured:
        full = np.concatenate(captured).astype(np.float32, copy=False)
        final_text = _transcribe_chunk(full, language=language)
    else:
        final_text = ""

    if not final_text:
        final_text = " ".join(partials).strip()

    if on_final:
        on_final(final_text)
    return final_text


def transcribe_wav_streaming(
    audio_path: str | Path,
    *,
    chunk_seconds: float = DEFAULT_CHUNK_SECONDS,
    language: str | None = "en",
    on_partial: Callable[[str], None] | None = None,
) -> str:
    """Stream a WAV file through the chunked pipeline. Used by smoke tests."""
    import soundfile as sf

    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != SAMPLE_RATE:
        # Cheap resample via numpy interp; good enough for smoke testing.
        ratio = SAMPLE_RATE / float(sr)
        target_len = int(round(data.shape[0] * ratio))
        if target_len > 0:
            x_old = np.linspace(0.0, 1.0, num=data.shape[0], endpoint=False)
            x_new = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
            data = np.interp(x_new, x_old, data).astype(np.float32)

    chunk_frames = int(SAMPLE_RATE * chunk_seconds)
    partials: list[str] = []
    for start in range(0, data.shape[0], chunk_frames):
        chunk = data[start : start + chunk_frames]
        if chunk.size == 0:
            continue
        if _rms(chunk) < DEFAULT_SILENCE_RMS:
            continue
        text = _transcribe_chunk(chunk, language=language)
        if text:
            partials.append(text)
            if on_partial:
                on_partial(" ".join(partials))

    if data.size:
        final = _transcribe_chunk(data, language=language)
        if final:
            return final
    return " ".join(partials).strip()


def iter_partials(
    *,
    max_seconds: float = 30.0,
    silence_seconds: float = 1.5,
    chunk_seconds: float = DEFAULT_CHUNK_SECONDS,
    silence_rms: float = DEFAULT_SILENCE_RMS,
    language: str | None = "en",
) -> Iterable[str]:
    """Generator wrapper: yields running transcript snapshots."""
    q: queue.Queue[str | None] = queue.Queue()

    def on_partial(text: str) -> None:
        q.put(text)

    def on_final(text: str) -> None:
        q.put(text)
        q.put(None)

    def run() -> None:
        try:
            transcribe_streaming(
                max_seconds=max_seconds,
                silence_seconds=silence_seconds,
                chunk_seconds=chunk_seconds,
                silence_rms=silence_rms,
                language=language,
                on_partial=on_partial,
                on_final=on_final,
            )
        except BaseException:  # noqa: BLE001
            q.put(None)
            raise

    threading.Thread(target=run, daemon=True).start()
    while True:
        item = q.get()
        if item is None:
            return
        yield item


__all__ = [
    "transcribe_streaming",
    "transcribe_wav_streaming",
    "iter_partials",
    "get_streaming_backend",
]
