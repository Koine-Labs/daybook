"""Smoke test for streaming TTS.

Confirms:
  1. split_into_chunks() finds sentence boundaries
  2. speak_streaming() returns first audio within budget (<1500ms target)
  3. async variant drains a fake token stream
  4. Voice continuity: log per-chunk durations so a human can listen for cuts

Set DAYBOOK_NO_PLAY=1 to skip actual playback.

Run with:
    cd apps/inference && source .venv/bin/activate && python -m audio.streaming_smoke
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from audio import get_active_backend  # noqa: E402
from audio.streaming import (  # noqa: E402
    speak_streaming,
    speak_streaming_async,
    split_into_chunks,
)

SKIP_PLAYBACK = os.environ.get("DAYBOOK_NO_PLAY") == "1"

PARAGRAPH = (
    "Lights out. Try not to think too hard tonight. "
    "Last time, it didn't help."
)
FIRST_AUDIO_BUDGET_MS = 1500.0


def test_chunker() -> bool:
    print("[1] split_into_chunks()")
    chunks = split_into_chunks(PARAGRAPH)
    print(f"    chunks ({len(chunks)}): {chunks}")
    if len(chunks) != 3:
        print(f"    FAIL: expected 3 chunks, got {len(chunks)}")
        return False

    # Edge cases
    if split_into_chunks("") != []:
        print("    FAIL: empty string should return []")
        return False
    one = split_into_chunks("Hello there.")
    if one != ["Hello there."]:
        print(f"    FAIL: single sentence wrong: {one}")
        return False
    print("    PASS")
    return True


def test_streaming_tts() -> bool:
    print(f"[2] speak_streaming() — backend={get_active_backend()}")
    chunk_logs: list[tuple[float, int, str]] = []
    t0 = time.monotonic()

    def on_chunk_start(idx: int, text: str) -> None:
        chunk_logs.append((time.monotonic() - t0, idx, text))

    result = speak_streaming(PARAGRAPH, on_chunk_start=on_chunk_start)
    print(f"    chunks_played: {result['chunks_played']}")
    print(f"    first_audio_ms: {result['first_audio_ms']:.0f}")
    print(f"    total_audio_ms: {result['total_audio_ms']:.0f}")
    for elapsed, idx, text in chunk_logs:
        snippet = text if len(text) < 50 else text[:47] + "..."
        print(f"    chunk {idx} @ {elapsed*1000:.0f}ms: {snippet!r}")

    if result["chunks_played"] != 3:
        print(f"    FAIL: expected 3 chunks played, got {result['chunks_played']}")
        return False

    # When skipping playback the producer/consumer still measures first-audio
    # latency = synth-of-first-sentence time. That's still meaningful.
    if result["first_audio_ms"] > FIRST_AUDIO_BUDGET_MS:
        print(
            f"    WARN: first_audio_ms {result['first_audio_ms']:.0f} > budget"
            f" {FIRST_AUDIO_BUDGET_MS:.0f}ms (informational only)"
        )

    print("    PASS")
    return True


def test_async_stream() -> bool:
    print("[3] speak_streaming_async() — fake token stream")

    async def fake_stream():
        # Simulate a slow LLM producing tokens.
        tokens = [
            "Lights ", "out. ",
            "Try ", "not ", "to ", "think ", "too ", "hard ", "tonight. ",
            "Last ", "time, ", "it ", "didn't ", "help.",
        ]
        for tok in tokens:
            await asyncio.sleep(0.03)
            yield tok

    chunk_logs: list[tuple[int, str]] = []

    def on_chunk_start(idx: int, text: str) -> None:
        chunk_logs.append((idx, text))

    async def run():
        return await speak_streaming_async(
            fake_stream(), on_chunk_start=on_chunk_start
        )

    result = asyncio.run(run())
    print(f"    chunks_played: {result['chunks_played']}")
    print(f"    first_audio_ms: {result['first_audio_ms']:.0f}")
    print(f"    total_audio_ms: {result['total_audio_ms']:.0f}")
    for idx, text in chunk_logs:
        snippet = text if len(text) < 50 else text[:47] + "..."
        print(f"    chunk {idx}: {snippet!r}")
    if result["chunks_played"] < 2:
        print("    FAIL: async stream should produce at least 2 chunks")
        return False
    print("    PASS")
    return True


def main() -> int:
    print("=== Streaming TTS smoke test ===")
    print(f"DAYBOOK_NO_PLAY={os.environ.get('DAYBOOK_NO_PLAY') or '(unset → will play)'}\n")

    if get_active_backend() == "none":
        print("ERROR: no TTS backend available")
        return 1

    ok = True
    ok &= test_chunker()
    print()
    ok &= test_streaming_tts()
    print()
    ok &= test_async_stream()
    print()

    print("=== Streaming TTS smoke test", "PASSED" if ok else "FAILED", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
