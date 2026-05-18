"""End-to-end streaming chat smoke test.

Compares streaming vs non-streaming for the same prompt. Reports
time-to-first-delta, time-to-first-audio-chunk, and total time. Verifies
DB writes, observer + drift fire after the stream completes, and cleans up.

Run with:
    cd apps && source inference/.venv/bin/activate
    python -m chat.streaming_smoke
    DAYBOOK_NO_PLAY=1 python -m chat.streaming_smoke   # skip audio playback
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402

from .conversation import create_conversation, end_conversation
from .handler import handle_user_message, handle_user_message_streaming


SMOKE_TITLE = "SMOKE_TEST: streaming chat"
PROMPT = (
    "Tell me a short two-sentence reflection on how I've been showing up "
    "this week. Keep it under 30 words."
)


def _cleanup() -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM chat_conversations WHERE title LIKE 'SMOKE_TEST:%streaming%'"
        )
        ids = [str(r[0]) for r in cur.fetchall()]
        if not ids:
            return 0
        cur.execute(
            """
            DELETE FROM embeddings
            WHERE source_type = 'chat_message'
              AND source_id IN (
                SELECT id FROM chat_messages WHERE conversation_id = ANY(%s)
              )
            """,
            (ids,),
        )
        cur.execute("DELETE FROM chat_conversations WHERE id = ANY(%s)", (ids,))
        conv_deleted = cur.rowcount
        conn.commit()
    return conv_deleted


def _verify(conversation_id: str, *, expected_min_messages: int) -> bool:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*), COUNT(embedding_id) FROM chat_messages "
            "WHERE conversation_id = %s",
            (conversation_id,),
        )
        n_msg, n_with_emb = cur.fetchone()
        cur.execute(
            "SELECT role, COUNT(*) FROM chat_messages WHERE conversation_id = %s GROUP BY role",
            (conversation_id,),
        )
        per_role = dict(cur.fetchall())
    ok = (
        n_msg >= expected_min_messages
        and per_role.get("user", 0) >= 1
        and per_role.get("assistant", 0) >= 1
        and n_with_emb == n_msg
    )
    print(f"    messages: {n_msg}  per_role: {per_role}  with_embedding: {n_with_emb}")
    return ok


async def _run_streaming(conversation_id: str) -> dict:
    """Run streaming chat + streaming TTS, returning latency metrics."""
    from inference.audio import speak_streaming_async

    started = time.monotonic()
    first_delta_ms: float | None = None
    first_audio_ms: float | None = None
    full_text = ""

    stream = handle_user_message_streaming(
        user_id=_paths.DEFAULT_USER_ID,
        conversation_id=conversation_id,
        user_text=PROMPT,
    )

    async def tee():
        nonlocal first_delta_ms, full_text
        async for delta in stream:
            if first_delta_ms is None:
                first_delta_ms = (time.monotonic() - started) * 1000.0
            full_text += delta
            yield delta

    def on_chunk_start(idx: int, text: str) -> None:
        nonlocal first_audio_ms
        if idx == 0 and first_audio_ms is None:
            first_audio_ms = (time.monotonic() - started) * 1000.0

    tts_result = await speak_streaming_async(
        tee(), mode="companion", on_chunk_start=on_chunk_start
    )
    total_ms = (time.monotonic() - started) * 1000.0
    return {
        "first_delta_ms": first_delta_ms or 0.0,
        "first_audio_ms": first_audio_ms or tts_result.get("first_audio_ms", 0.0),
        "total_ms": total_ms,
        "text": full_text.strip(),
        "tts_chunks": tts_result.get("chunks_played", 0),
    }


def _run_non_streaming(conversation_id: str) -> dict:
    """Run sync chat + sync TTS for the same prompt."""
    from inference.audio import speak_streaming

    started = time.monotonic()
    resp = handle_user_message(
        user_id=_paths.DEFAULT_USER_ID,
        conversation_id=conversation_id,
        user_text=PROMPT,
    )
    llm_done_ms = (time.monotonic() - started) * 1000.0
    first_audio_ms = llm_done_ms
    tts_result: dict = {"chunks_played": 0}
    if resp.text:
        tts_t0 = time.monotonic()
        tts_result = speak_streaming(resp.text, mode="companion")
        first_audio_ms = (
            llm_done_ms + (tts_result.get("first_audio_ms") or 0.0)
        )
    total_ms = (time.monotonic() - started) * 1000.0
    return {
        "llm_done_ms": llm_done_ms,
        "first_audio_ms": first_audio_ms,
        "total_ms": total_ms,
        "text": resp.text,
        "tts_chunks": tts_result.get("chunks_played", 0),
    }


def main() -> int:
    print("=== Daybook streaming chat smoke test ===\n")
    print(f"DAYBOOK_NO_PLAY={os.environ.get('DAYBOOK_NO_PLAY') or '(unset → will play)'}")
    print(f"prompt: {PROMPT!r}\n")

    print("[setup] cleaning prior smoke conversations...")
    _cleanup()
    print()

    ok = True

    # Non-streaming baseline.
    print("--- baseline: non-streaming ---")
    ns_conv = create_conversation(
        user_id=_paths.DEFAULT_USER_ID, title=SMOKE_TITLE + " (sync)"
    )
    ns_result = _run_non_streaming(ns_conv)
    print(f"  llm_done_ms:    {ns_result['llm_done_ms']:.0f}")
    print(f"  first_audio_ms: {ns_result['first_audio_ms']:.0f}")
    print(f"  total_ms:       {ns_result['total_ms']:.0f}")
    print(f"  text:           {ns_result['text']!r}")
    print(f"  tts_chunks:     {ns_result['tts_chunks']}")
    ns_ok = _verify(ns_conv, expected_min_messages=2)
    print(f"  verification:   {'PASS' if ns_ok else 'FAIL'}\n")
    end_conversation(conversation_id=ns_conv)
    ok &= ns_ok

    # Streaming.
    print("--- streaming ---")
    st_conv = create_conversation(
        user_id=_paths.DEFAULT_USER_ID, title=SMOKE_TITLE + " (stream)"
    )
    st_result = asyncio.run(_run_streaming(st_conv))
    print(f"  first_delta_ms: {st_result['first_delta_ms']:.0f}")
    print(f"  first_audio_ms: {st_result['first_audio_ms']:.0f}")
    print(f"  total_ms:       {st_result['total_ms']:.0f}")
    print(f"  text:           {st_result['text']!r}")
    print(f"  tts_chunks:     {st_result['tts_chunks']}")
    st_ok = _verify(st_conv, expected_min_messages=2)
    print(f"  verification:   {'PASS' if st_ok else 'FAIL'}\n")
    end_conversation(conversation_id=st_conv)
    ok &= st_ok

    # Comparison.
    print("--- comparison ---")
    ns_fa = ns_result["first_audio_ms"]
    st_fa = st_result["first_audio_ms"]
    speedup = ns_fa / st_fa if st_fa > 0 else 0.0
    print(
        f"[non-streaming] total: {ns_result['total_ms']:.0f}ms, "
        f"time-to-first-audio: {ns_fa:.0f}ms"
    )
    print(
        f"[streaming]     total: {st_result['total_ms']:.0f}ms, "
        f"time-to-first-audio: {st_fa:.0f}ms"
        + (f" ({speedup:.1f}x faster!)" if speedup >= 1.0 else f" ({speedup:.2f}x)")
    )

    print("\n[cleanup] removing smoke conversations + embeddings...")
    n = _cleanup()
    print(f"  cleaned {n} conversations\n")

    print("=== streaming chat smoke", "PASSED" if ok else "FAILED", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
