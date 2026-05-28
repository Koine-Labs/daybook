"""Sentence-chunked streaming TTS.

Cuts conversational latency by synthesizing each sentence as a separate chunk
and playing chunks as they land, while later sentences synthesize in parallel.

Public surface:
  - speak_streaming(text, ...)          -> dict   (sync, text in)
  - speak_streaming_async(text_stream)  -> dict   (async, token stream in)
  - split_into_chunks(text)             -> list[str]
"""
from __future__ import annotations

import asyncio
import os
import queue
import re
import threading
import time
from typing import AsyncIterator, Callable

from .player import play
from .tts_router import MODE_COMPANION, Mode, synthesize


_SKIP_PLAYBACK_ENV = "DAYBOOK_NO_PLAY"

# Patterns to strip from text before TTS so the synth doesn't read out literal
# markdown characters ("asterisk asterisk Reh-jis asterisk asterisk"). Stored
# text + printed text keep their formatting; only the voice path is cleaned.
_TTS_STRIP_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\*\*([^*]+?)\*\*"), r"\1"),       # **bold**  -> bold
    (re.compile(r"__([^_]+?)__"), r"\1"),            # __bold__  -> bold
    (re.compile(r"(?<!\*)\*([^*\s][^*]*?)\*(?!\*)"), r"\1"),  # *italic*  -> italic
    (re.compile(r"(?<!_)_([^_\s][^_]*?)_(?!_)"), r"\1"),      # _italic_  -> italic
    (re.compile(r"`([^`]+?)`"), r"\1"),              # `code`    -> code
    (re.compile(r"~~([^~]+?)~~"), r"\1"),            # ~~strike~~-> strike
    (re.compile(r"!?\[([^\]]+?)\]\([^)]+?\)"), r"\1"),  # [text](url) -> text
    (re.compile(r"^#{1,6}\s+", re.MULTILINE), ""),  # # heading -> heading
    (re.compile(r"^>\s+", re.MULTILINE), ""),       # > quote   -> quote
    (re.compile(r"^[-*+]\s+", re.MULTILINE), ""),   # - bullet  -> bullet
]


def strip_markdown_for_tts(text: str) -> str:
    """Strip markdown formatting so TTS doesn't pronounce literal asterisks etc."""
    out = text
    for pattern, repl in _TTS_STRIP_PATTERNS:
        out = pattern.sub(repl, out)
    return out


# Match end-of-sentence punctuation followed by whitespace. Captures the trailing
# punctuation so we can keep it attached to its sentence. Good enough for English
# without dragging in an NLP dependency.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# Also split on these "soft" pauses if a sentence would otherwise produce a
# too-long chunk — keeps per-chunk synth time bounded so interrupts are snappy.
_SOFT_SPLIT_RE = re.compile(r"(?<=[,;:—–-])\s+")
# Hard cap on chunk size (chars). Anything longer gets split on soft boundaries.
# 80 chars ≈ 12-15 words ≈ ~600ms Kokoro synth ≈ snappy interrupt latency.
_MAX_CHUNK_CHARS = 80
# Async streamer holds short fragments until at least this many chars have
# accumulated before emitting — keeps single tokens like "Oh." from becoming
# their own synth call. Sync chunker ignores this (already has full text).
_MIN_CHUNK_CHARS = 4


def _subdivide_long_chunk(chunk: str) -> list[str]:
    """If a chunk exceeds _MAX_CHUNK_CHARS, split it at soft pauses (commas etc.)
    and if still too long, hard-split at the nearest word boundary."""
    if len(chunk) <= _MAX_CHUNK_CHARS:
        return [chunk]
    parts = [p.strip() for p in _SOFT_SPLIT_RE.split(chunk) if p and p.strip()]
    out: list[str] = []
    for p in parts:
        if len(p) <= _MAX_CHUNK_CHARS:
            out.append(p)
            continue
        # Still too long — hard split at word boundary near the cap.
        words = p.split()
        cur = ""
        for w in words:
            if cur and len(cur) + 1 + len(w) > _MAX_CHUNK_CHARS:
                out.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}" if cur else w
        if cur:
            out.append(cur)
    return out

# Process-wide interruption state — kept in sys.modules under a fixed key so
# that if streaming.py gets imported under two paths (audio.streaming vs
# inference.audio.streaming), both copies share the SAME events. Without this,
# stop_speaking() from one import path silently fails to interrupt the other.
def _shared_audio_state():
    import sys
    import types
    key = "__daybook_audio_shared_state__"
    if key not in sys.modules:
        m = types.ModuleType(key)
        m.SPEAKING = threading.Event()
        m.STOP_REQUESTED = threading.Event()
        sys.modules[key] = m
    return sys.modules[key]


_AUDIO_STATE = _shared_audio_state()
_SPEAKING: threading.Event = _AUDIO_STATE.SPEAKING
_STOP_REQUESTED: threading.Event = _AUDIO_STATE.STOP_REQUESTED


def is_speaking() -> bool:
    """True while a speak_streaming call is actively producing/playing audio."""
    return _SPEAKING.is_set()


def stop_speaking() -> None:
    """Interrupt any in-flight speak_streaming call. Stops current chunk and
    skips any remaining queued chunks. Best-effort: callers should expect
    a small tail of audio still to drain through the hardware buffer."""
    import logging
    _log = logging.getLogger(__name__)
    was_speaking = _SPEAKING.is_set()
    _STOP_REQUESTED.set()
    try:
        import sounddevice as sd

        sd.stop()
    except Exception:
        pass
    if was_speaking:
        _log.info("stop_speaking() called while _SPEAKING was set — interrupt should fire")
    else:
        _log.warning("stop_speaking() called but _SPEAKING was NOT set — nothing was active to interrupt")


def _play_interruptible(audio_bytes: bytes) -> bool:
    """Play audio with ~50ms granularity to check _STOP_REQUESTED.

    Non-blocking play + a poll loop so sd.stop() takes effect within ~50ms
    of the interrupt request, regardless of OS buffering. Crucially does
    NOT call sd.wait() — that would block until the (now-stopped) stream's
    OS buffer drains, which on macOS BT can be 500ms+.

    Returns True if interrupted, False if completed naturally.
    """
    import io
    import sounddevice as sd
    import soundfile as sf
    import time

    with io.BytesIO(audio_bytes) as buf:
        data, sample_rate = sf.read(buf, dtype="float32", always_2d=False)

    sd.play(data, samplerate=sample_rate, blocking=False)
    while True:
        if _STOP_REQUESTED.is_set():
            sd.stop()
            return True
        stream = sd.get_stream()
        if stream is None or not stream.active:
            return False
        time.sleep(0.05)


def split_into_chunks(text: str) -> list[str]:
    """Split text into sentence-ish chunks, then subdivide any over the size cap
    so per-chunk synth time stays bounded (helps interrupt latency)."""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p and p.strip()]
    if not parts:
        parts = [text]
    out: list[str] = []
    for p in parts:
        out.extend(_subdivide_long_chunk(p))
    return out


def _skip_playback() -> bool:
    return os.environ.get(_SKIP_PLAYBACK_ENV) == "1"


def speak_streaming(
    text: str,
    *,
    mode: Mode = MODE_COMPANION,
    voice: str | None = None,
    speed: float | None = None,
    on_chunk_start: Callable[[int, str], None] | None = None,
) -> dict:
    """Stream-synthesize a paragraph; play each sentence as soon as it lands.

    Returns dict with first_audio_ms, total_audio_ms, chunks_played, chunks.
    """
    chunks = split_into_chunks(text)
    started_at = time.monotonic()

    if not chunks:
        return {
            "first_audio_ms": 0.0,
            "total_audio_ms": 0.0,
            "chunks_played": 0,
            "chunks": [],
            "interrupted": False,
        }

    _STOP_REQUESTED.clear()
    _SPEAKING.set()
    interrupted = False
    try:
        # If the input is one sentence, the producer thread is pure overhead.
        if len(chunks) == 1:
            chunk = chunks[0]
            if on_chunk_start:
                on_chunk_start(0, chunk)
            wav = synthesize(strip_markdown_for_tts(chunk), mode=mode, voice=voice, speed=speed)
            first_audio_ms = (time.monotonic() - started_at) * 1000.0
            if not _skip_playback() and not _STOP_REQUESTED.is_set():
                play(wav)
            if _STOP_REQUESTED.is_set():
                interrupted = True
            total_ms = (time.monotonic() - started_at) * 1000.0
            return {
                "first_audio_ms": first_audio_ms,
                "total_audio_ms": total_ms,
                "chunks_played": 0 if interrupted else 1,
                "chunks": chunks,
                "interrupted": interrupted,
            }

        # Producer synthesizes chunks ahead of playback. Consumer (this thread)
        # plays them sequentially as they appear.
        audio_q: queue.Queue = queue.Queue(maxsize=4)
        producer_error: list[BaseException] = []

        def produce() -> None:
            try:
                for idx, chunk in enumerate(chunks):
                    if _STOP_REQUESTED.is_set():
                        break
                    wav = synthesize(strip_markdown_for_tts(chunk), mode=mode, voice=voice, speed=speed)
                    audio_q.put((idx, chunk, wav))
            except BaseException as exc:  # noqa: BLE001
                producer_error.append(exc)
            finally:
                audio_q.put(None)

        producer = threading.Thread(target=produce, daemon=True)
        producer.start()

        first_audio_ms = 0.0
        chunks_played = 0
        skip = _skip_playback()

        while True:
            item = audio_q.get()
            if item is None:
                break
            if _STOP_REQUESTED.is_set():
                interrupted = True
                # Drain remaining queue items without playing
                while item is not None:
                    try:
                        item = audio_q.get_nowait()
                    except queue.Empty:
                        break
                break
            idx, chunk_text, wav = item
            if chunks_played == 0:
                first_audio_ms = (time.monotonic() - started_at) * 1000.0
            if on_chunk_start:
                on_chunk_start(idx, chunk_text)
            if not skip:
                play(wav)
            chunks_played += 1

        producer.join(timeout=1.0)
        if producer_error and not interrupted:
            raise producer_error[0]

        total_ms = (time.monotonic() - started_at) * 1000.0
        return {
            "first_audio_ms": first_audio_ms,
            "total_audio_ms": total_ms,
            "chunks_played": chunks_played,
            "chunks": chunks,
            "interrupted": interrupted,
        }
    finally:
        _SPEAKING.clear()
        _STOP_REQUESTED.clear()


async def speak_streaming_async(
    text_stream: AsyncIterator[str],
    *,
    mode: Mode = MODE_COMPANION,
    voice: str | None = None,
    speed: float | None = None,
    on_chunk_start: Callable[[int, str], None] | None = None,
) -> dict:
    """Consume an async text stream, emit + play as sentence boundaries land.

    Honors stop_speaking() — checks _STOP_REQUESTED before consuming each
    token, before synthesizing each pending chunk, and before playing each
    chunk. Sets _SPEAKING for the duration so is_speaking() reports correctly
    (required for the barge-in detector in mic_listener to fire).
    """
    started_at = time.monotonic()
    loop = asyncio.get_running_loop()

    buffer = ""
    pending: list[str] = []
    first_audio_ms = 0.0
    chunks_played = 0
    skip = _skip_playback()
    interrupted = False

    async def synth_and_play(idx: int, chunk: str) -> tuple[float, bool]:
        """Returns (landed_ts, was_interrupted)."""
        if _STOP_REQUESTED.is_set():
            return time.monotonic(), True
        clean_chunk = strip_markdown_for_tts(chunk)
        wav = await loop.run_in_executor(
            None,
            lambda: synthesize(clean_chunk, mode=mode, voice=voice, speed=speed),
        )
        landed = time.monotonic()
        if _STOP_REQUESTED.is_set():
            return landed, True
        if on_chunk_start:
            on_chunk_start(idx, chunk)
        if not skip:
            # Use interruptible play (50ms poll granularity) instead of
            # blocking play, so sd.stop() actually cuts mid-sentence.
            interrupted_in_play = await loop.run_in_executor(
                None, _play_interruptible, wav
            )
            if interrupted_in_play:
                return landed, True
        return landed, _STOP_REQUESTED.is_set()

    def flush_complete(force: bool) -> list[str]:
        nonlocal buffer
        out: list[str] = []
        parts = _SENTENCE_SPLIT_RE.split(buffer)
        if not force:
            # Last fragment may be incomplete; hold it back until more text or end.
            tail = parts.pop() if parts else ""
        else:
            tail = ""
        for p in parts:
            p = p.strip()
            if p and (force or len(p) >= _MIN_CHUNK_CHARS):
                # Subdivide long sentences so synth stays interruptible.
                out.extend(_subdivide_long_chunk(p))
        buffer = tail
        # Also: if the buffer itself has grown too long without a sentence
        # boundary, flush it via soft-split to avoid waiting forever for
        # the period that never comes.
        if len(buffer) > _MAX_CHUNK_CHARS * 2:
            soft = _SOFT_SPLIT_RE.split(buffer)
            if len(soft) > 1:
                # Keep last as tail; flush the rest
                tail2 = soft.pop()
                for p in soft:
                    p = p.strip()
                    if p:
                        out.extend(_subdivide_long_chunk(p))
                buffer = tail2
        return out

    _STOP_REQUESTED.clear()
    _SPEAKING.set()
    try:
        async for token in text_stream:
            if _STOP_REQUESTED.is_set():
                interrupted = True
                break
            if not token:
                continue
            buffer += token
            for chunk in flush_complete(force=False):
                pending.append(chunk)

            while pending:
                if _STOP_REQUESTED.is_set():
                    interrupted = True
                    pending.clear()
                    break
                chunk = pending.pop(0)
                idx = chunks_played
                landed, was_interrupted = await synth_and_play(idx, chunk)
                if chunks_played == 0:
                    first_audio_ms = (landed - started_at) * 1000.0
                if was_interrupted:
                    interrupted = True
                    pending.clear()
                    break
                chunks_played += 1
            if interrupted:
                break

        # Drain remainder unless interrupted.
        if not interrupted and buffer.strip():
            pending.extend(flush_complete(force=True))
        while pending and not interrupted:
            if _STOP_REQUESTED.is_set():
                interrupted = True
                pending.clear()
                break
            chunk = pending.pop(0)
            idx = chunks_played
            landed, was_interrupted = await synth_and_play(idx, chunk)
            if chunks_played == 0:
                first_audio_ms = (landed - started_at) * 1000.0
            if was_interrupted:
                interrupted = True
                pending.clear()
                break
            chunks_played += 1
    finally:
        _SPEAKING.clear()
        _STOP_REQUESTED.clear()

    total_ms = (time.monotonic() - started_at) * 1000.0
    return {
        "first_audio_ms": first_audio_ms,
        "total_audio_ms": total_ms,
        "chunks_played": chunks_played,
        "interrupted": interrupted,
    }


__all__ = [
    "speak_streaming",
    "speak_streaming_async",
    "split_into_chunks",
    "is_speaking",
    "stop_speaking",
]
