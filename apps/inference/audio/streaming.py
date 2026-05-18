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

# Match end-of-sentence punctuation followed by whitespace. Captures the trailing
# punctuation so we can keep it attached to its sentence. Good enough for English
# without dragging in an NLP dependency.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# Async streamer holds short fragments until at least this many chars have
# accumulated before emitting — keeps single tokens like "Oh." from becoming
# their own synth call. Sync chunker ignores this (already has full text).
_MIN_CHUNK_CHARS = 4


def split_into_chunks(text: str) -> list[str]:
    """Split text into sentence-ish chunks using simple regex."""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p and p.strip()]
    return parts or [text]


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
        }

    # If the input is one sentence, the producer thread is pure overhead.
    if len(chunks) == 1:
        chunk = chunks[0]
        if on_chunk_start:
            on_chunk_start(0, chunk)
        wav = synthesize(chunk, mode=mode, voice=voice, speed=speed)
        first_audio_ms = (time.monotonic() - started_at) * 1000.0
        if not _skip_playback():
            play(wav)
        total_ms = (time.monotonic() - started_at) * 1000.0
        return {
            "first_audio_ms": first_audio_ms,
            "total_audio_ms": total_ms,
            "chunks_played": 1,
            "chunks": chunks,
        }

    # Producer synthesizes chunks ahead of playback. Consumer (this thread)
    # plays them sequentially as they appear.
    audio_q: queue.Queue = queue.Queue(maxsize=4)
    producer_error: list[BaseException] = []

    def produce() -> None:
        try:
            for idx, chunk in enumerate(chunks):
                wav = synthesize(chunk, mode=mode, voice=voice, speed=speed)
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
        idx, chunk_text, wav = item
        if chunks_played == 0:
            first_audio_ms = (time.monotonic() - started_at) * 1000.0
        if on_chunk_start:
            on_chunk_start(idx, chunk_text)
        if not skip:
            play(wav)
        chunks_played += 1

    producer.join(timeout=1.0)
    if producer_error:
        raise producer_error[0]

    total_ms = (time.monotonic() - started_at) * 1000.0
    return {
        "first_audio_ms": first_audio_ms,
        "total_audio_ms": total_ms,
        "chunks_played": chunks_played,
        "chunks": chunks,
    }


async def speak_streaming_async(
    text_stream: AsyncIterator[str],
    *,
    mode: Mode = MODE_COMPANION,
    voice: str | None = None,
    speed: float | None = None,
    on_chunk_start: Callable[[int, str], None] | None = None,
) -> dict:
    """Consume an async text stream, emit + play as sentence boundaries land."""
    started_at = time.monotonic()
    loop = asyncio.get_running_loop()

    buffer = ""
    pending: list[str] = []
    first_audio_ms = 0.0
    chunks_played = 0
    skip = _skip_playback()

    async def synth_and_play(idx: int, chunk: str) -> float:
        wav = await loop.run_in_executor(
            None,
            lambda: synthesize(chunk, mode=mode, voice=voice, speed=speed),
        )
        landed = time.monotonic()
        if on_chunk_start:
            on_chunk_start(idx, chunk)
        if not skip:
            await loop.run_in_executor(None, play, wav)
        return landed

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
                out.append(p)
        buffer = tail
        return out

    async for token in text_stream:
        if not token:
            continue
        buffer += token
        for chunk in flush_complete(force=False):
            pending.append(chunk)

        while pending:
            chunk = pending.pop(0)
            idx = chunks_played
            landed = await synth_and_play(idx, chunk)
            if chunks_played == 0:
                first_audio_ms = (landed - started_at) * 1000.0
            chunks_played += 1

    # Drain remainder.
    if buffer.strip():
        pending.extend(flush_complete(force=True))
    while pending:
        chunk = pending.pop(0)
        idx = chunks_played
        landed = await synth_and_play(idx, chunk)
        if chunks_played == 0:
            first_audio_ms = (landed - started_at) * 1000.0
        chunks_played += 1

    total_ms = (time.monotonic() - started_at) * 1000.0
    return {
        "first_audio_ms": first_audio_ms,
        "total_audio_ms": total_ms,
        "chunks_played": chunks_played,
    }


__all__ = [
    "speak_streaming",
    "speak_streaming_async",
    "split_into_chunks",
]
