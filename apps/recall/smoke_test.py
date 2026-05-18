"""End-to-end smoke test for the recall capture flow.

Run with:
    cd apps && source inference/.venv/bin/activate && python -m recall.smoke_test

Asserts:
  1. capture(text=...) returns a DreamCapture with row id and embedding id
  2. depth classifier matches expected (19 words => FRAGMENT)
  3. dream_recalls row exists in DB
  4. embeddings row exists in DB
  5. retrieve_similar finds the just-stored dream
  6. capture(ack=False) skips LLM call
Cleans up all rows tagged with SMOKE_TEST: prefix at the end.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Path setup so we can import recall + inference utilities
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
INFERENCE_DIR = Path(__file__).resolve().parent.parent / "inference"
sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402
from embeddings import retrieve_similar  # noqa: E402

from recall.capture import DEFAULT_USER_ID, capture, depth_from_text  # noqa: E402


SMOKE_PREFIX = "SMOKE_TEST: "
TEST_DREAM = (
    SMOKE_PREFIX
    + "I dreamed I was swimming under a starlit sky. "
    + "My grandfather was at the shore, watching but not speaking."
)
TEST_DREAM_NO_ACK = (
    SMOKE_PREFIX + "A short dream about a long hallway with one open door."
)


def _count_dream_recalls(dream_id: str) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM dream_recalls WHERE id = %s", (dream_id,))
        return int(cur.fetchone()[0])


def _count_embeddings(source_id: str) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM embeddings WHERE source_id = %s AND source_type = 'dream_recall'",
            (source_id,),
        )
        return int(cur.fetchone()[0])


def _cleanup() -> tuple[int, int]:
    """Delete all SMOKE_TEST: rows from dream_recalls + their embeddings."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM dream_recalls WHERE raw_text LIKE %s",
            (SMOKE_PREFIX + "%",),
        )
        ids = [str(r[0]) for r in cur.fetchall()]
        if ids:
            cur.execute(
                "DELETE FROM embeddings WHERE source_type = 'dream_recall' AND source_id = ANY(%s::uuid[])",
                (ids,),
            )
            emb_deleted = cur.rowcount
            cur.execute("DELETE FROM dream_recalls WHERE id = ANY(%s::uuid[])", (ids,))
            dr_deleted = cur.rowcount
        else:
            emb_deleted = 0
            dr_deleted = 0
        conn.commit()
    return dr_deleted, emb_deleted


def main() -> int:
    print("=== Daybook recall capture smoke test ===\n")

    # Pre-cleanup in case a previous run left junk
    pre_dr, pre_em = _cleanup()
    if pre_dr or pre_em:
        print(f"(pre-clean: removed {pre_dr} dream_recalls + {pre_em} embeddings)\n")

    # --- Test 0: depth_from_text classifier ---
    print("[Test 0] depth_from_text() word-count heuristic")
    cases = {
        "": "NONE",
        "I dreamed nothing.": "NONE",  # 3 words
        " ".join(["w"] * 10): "FRAGMENT",
        " ".join(["w"] * 40): "SCENE",
        " ".join(["w"] * 150): "NARRATIVE",
    }
    for txt, expected in cases.items():
        got = depth_from_text(txt)
        ok = "OK" if got == expected else "FAIL"
        print(f"  [{ok}] {len(txt.split())} words -> {got} (expected {expected})")
        assert got == expected, f"depth_from_text failed: {txt!r}"
    print()

    # --- Test 1: full capture (text + embed + LLM ack) ---
    print("[Test 1] capture(text=..., ack=True) — full pipeline")
    result = capture(text=TEST_DREAM, ack=True)
    print(f"  dream_recall_id: {result.dream_recall_id}")
    print(f"  embedding_id:    {result.embedding_id}")
    print(f"  depth:           {result.depth}  (expected FRAGMENT, ~21 words after prefix)")
    print(f"  text:            {result.text[:80]}...")
    print(f"  Regis:           {result.regis_utterance!r}")
    if result.composition_seconds is not None:
        print(f"  compose time:    {result.composition_seconds*1000:.0f}ms")
    if result.embed_error:
        print(f"  embed_error:     {result.embed_error}")
    if result.compose_error:
        print(f"  compose_error:   {result.compose_error}")

    # Word count: SMOKE_PREFIX is 2 words + dream is 19 = 21 -> FRAGMENT
    word_count = len(TEST_DREAM.split())
    print(f"  word count of test dream (incl. prefix): {word_count}")
    assert result.depth == "FRAGMENT", f"Expected FRAGMENT, got {result.depth}"
    assert result.dream_recall_id, "dream_recall_id missing"

    # Verify DB rows
    assert _count_dream_recalls(result.dream_recall_id) == 1, "dream_recalls row missing"
    print("  dream_recalls row: present in DB")
    if result.embedding_id:
        assert _count_embeddings(result.dream_recall_id) == 1, "embeddings row missing"
        print("  embeddings row:    present in DB")
    else:
        print("  embeddings row:    SKIPPED (embed failed)")

    # --- Test 2: similarity retrieval finds it ---
    print("\n[Test 2] retrieve_similar() finds the just-stored dream")
    hits = retrieve_similar(
        "swimming under stars with grandfather",
        user_id=DEFAULT_USER_ID,
        top_k=5,
        source_types=["dream_recall"],
    )
    print(f"  got {len(hits)} hits")
    found = any(h.source_id == result.dream_recall_id for h in hits)
    for h in hits[:5]:
        marker = " <-- our dream" if h.source_id == result.dream_recall_id else ""
        print(f"   sim={h.similarity:.3f}  {h.source_id}{marker}")
    assert found, "retrieve_similar did not return our dream in top 5"
    print("  found our dream in top-5: OK")

    # --- Test 3: no-ack path skips LLM call ---
    print("\n[Test 3] capture(text=..., ack=False) — no LLM call")
    result2 = capture(text=TEST_DREAM_NO_ACK, ack=False)
    print(f"  dream_recall_id: {result2.dream_recall_id}")
    print(f"  Regis:           {result2.regis_utterance!r}  (expected None)")
    print(f"  compose_error:   {result2.compose_error}      (expected None)")
    print(f"  depth:           {result2.depth}")
    assert result2.regis_utterance is None, "ack=False should NOT call LLM"
    assert result2.compose_error is None, "ack=False should NOT touch composer"
    assert _count_dream_recalls(result2.dream_recall_id) == 1, "no-ack dream missing in DB"
    print("  ack=False correctly skipped Regis")

    # --- Test 4: depth classifier on real captures ---
    print("\n[Test 4] depth boundaries cross-check on real captures")
    print(f"  test 1 dream words={word_count} depth={result.depth}")
    print(f"  test 2 dream words={len(TEST_DREAM_NO_ACK.split())} depth={result2.depth}")

    # --- Test 5: imports for recorder/whisper don't crash ---
    print("\n[Test 5] import recorder + whisper_client (audio path not actually exercised)")
    try:
        from recall import recorder  # noqa: F401
        from recall import whisper_client  # noqa: F401

        print("  imports OK")
    except Exception as e:
        print(f"  import FAILED: {e}")
        raise

    # --- Cleanup ---
    print("\n[cleanup] Removing SMOKE_TEST: rows")
    dr_deleted, em_deleted = _cleanup()
    print(f"  deleted {dr_deleted} dream_recalls and {em_deleted} embeddings")

    print("\n=== Smoke test complete (all assertions passed) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
