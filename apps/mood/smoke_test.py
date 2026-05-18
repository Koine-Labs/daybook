"""End-to-end smoke test for the mood capture flow.

Run with:
    cd apps && source inference/.venv/bin/activate && python -m mood.smoke_test

Asserts:
  1. log_mood() with notes returns dict with mood_id + embedding_id
  2. mood_reports row exists
  3. embeddings row exists when notes are present
  4. log_mood() without notes skips embedding
  5. valence/arousal bounds validated
Cleans up all rows whose notes start with SMOKE_PREFIX.
"""
from __future__ import annotations

import sys
from pathlib import Path

APPS_DIR = Path(__file__).resolve().parent.parent
INFERENCE_DIR = APPS_DIR / "inference"
for p in (APPS_DIR, INFERENCE_DIR):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from db import get_conn  # noqa: E402
from embeddings import retrieve_similar  # noqa: E402

from mood.capture import DEFAULT_USER_ID, log_mood  # noqa: E402


SMOKE_PREFIX = "SMOKE_TEST: "
TEST_NOTES = SMOKE_PREFIX + "tired but content, ready to wind down"


def _count_moods(mood_id: str) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM mood_reports WHERE id = %s", (mood_id,))
        return int(cur.fetchone()[0])


def _count_embeddings(source_id: str) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM embeddings WHERE source_id = %s AND source_type = 'mood'",
            (source_id,),
        )
        return int(cur.fetchone()[0])


def _cleanup() -> tuple[int, int]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM mood_reports WHERE notes LIKE %s",
            (SMOKE_PREFIX + "%",),
        )
        ids = [str(r[0]) for r in cur.fetchall()]
        if ids:
            cur.execute(
                "DELETE FROM embeddings WHERE source_type = 'mood' AND source_id = ANY(%s::uuid[])",
                (ids,),
            )
            emb_deleted = cur.rowcount
            cur.execute("DELETE FROM mood_reports WHERE id = ANY(%s::uuid[])", (ids,))
            mr_deleted = cur.rowcount
        else:
            emb_deleted = 0
            mr_deleted = 0
        conn.commit()
    return mr_deleted, emb_deleted


def main() -> int:
    print("=== Daybook mood capture smoke test ===\n")

    pre_mr, pre_em = _cleanup()
    if pre_mr or pre_em:
        print(f"(pre-clean: removed {pre_mr} mood_reports + {pre_em} embeddings)\n")

    print("[Test 1] log_mood(valence, arousal, notes) — full pipeline with embed")
    result = log_mood(user_id=DEFAULT_USER_ID, valence=0.3, arousal=-0.5, notes=TEST_NOTES)
    print(f"  mood_id:      {result['mood_id']}")
    print(f"  embedding_id: {result['embedding_id']}")
    print(f"  reported_at:  {result['reported_at'].isoformat()}")
    print(f"  valence:      {result['valence']:+.2f}")
    print(f"  arousal:      {result['arousal']:+.2f}")
    print(f"  notes:        {result['notes']!r}")

    assert result["mood_id"], "mood_id missing"
    assert _count_moods(result["mood_id"]) == 1, "mood_reports row missing"
    print("  mood_reports: present in DB")

    assert result["embedding_id"], "embedding_id missing when notes present"
    assert _count_embeddings(result["mood_id"]) == 1, "embeddings row missing"
    print("  embeddings:   present in DB (source_type='mood')")

    print("\n[Test 2] retrieve_similar finds the mood notes")
    hits = retrieve_similar(
        "tired ready to sleep",
        user_id=DEFAULT_USER_ID,
        top_k=5,
        source_types=["mood"],
    )
    print(f"  got {len(hits)} hits")
    found = any(h.source_id == result["mood_id"] for h in hits)
    for h in hits[:5]:
        marker = " <-- our mood" if h.source_id == result["mood_id"] else ""
        print(f"   sim={h.similarity:.3f}  {h.source_id}{marker}")
    assert found, "retrieve_similar did not return our mood in top 5"
    print("  found our mood in top-5: OK")

    print("\n[Test 3] log_mood without notes -> no embedding")
    result2 = log_mood(user_id=DEFAULT_USER_ID, valence=-0.1, arousal=0.4, notes="")
    print(f"  mood_id:      {result2['mood_id']}")
    print(f"  embedding_id: {result2['embedding_id']}  (expected None)")
    assert result2["embedding_id"] is None, "embedding should be None with empty notes"
    assert _count_moods(result2["mood_id"]) == 1, "mood row missing"

    print("\n[Test 4] validation: out-of-range raises")
    for kw in ({"valence": 1.5, "arousal": 0.0}, {"valence": 0.0, "arousal": -2.0}):
        try:
            log_mood(user_id=DEFAULT_USER_ID, notes="", **kw)
        except ValueError as e:
            print(f"  raised as expected for {kw}: {e}")
        else:
            raise AssertionError(f"log_mood should raise for {kw}")

    print("\n[cleanup] Removing SMOKE_TEST: + bare rows")
    # First remove the explicit no-notes row by id
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM mood_reports WHERE id = %s", (result2["mood_id"],))
        conn.commit()
    mr_deleted, em_deleted = _cleanup()
    print(f"  deleted {mr_deleted} mood_reports (notes-tagged) and {em_deleted} embeddings")
    print(f"  also removed the bare no-notes test row")

    print("\n=== Smoke test complete (all assertions passed) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
