"""End-to-end smoke test for the intent capture flow.

Run with:
    cd apps && source inference/.venv/bin/activate && python -m intent.smoke_test

Asserts:
  1. set_intent() returns a dict with intent_id + embedding_id
  2. intents row exists in DB
  3. embeddings row exists in DB (source_type='intent')
  4. retrieve_similar finds the just-stored intent
Cleans up all rows whose intent_text starts with SMOKE_PREFIX.
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

from intent.capture import DEFAULT_USER_ID, set_intent  # noqa: E402


SMOKE_PREFIX = "SMOKE_TEST: "
TEST_INTENT = SMOKE_PREFIX + "remember the colors of the lighthouse tonight"


def _count_intents(intent_id: str) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM intents WHERE id = %s", (intent_id,))
        return int(cur.fetchone()[0])


def _count_embeddings(source_id: str) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM embeddings WHERE source_id = %s AND source_type = 'intent'",
            (source_id,),
        )
        return int(cur.fetchone()[0])


def _cleanup() -> tuple[int, int]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM intents WHERE intent_text LIKE %s",
            (SMOKE_PREFIX + "%",),
        )
        ids = [str(r[0]) for r in cur.fetchall()]
        if ids:
            cur.execute(
                "DELETE FROM embeddings WHERE source_type = 'intent' AND source_id = ANY(%s::uuid[])",
                (ids,),
            )
            emb_deleted = cur.rowcount
            cur.execute("DELETE FROM intents WHERE id = ANY(%s::uuid[])", (ids,))
            in_deleted = cur.rowcount
        else:
            emb_deleted = 0
            in_deleted = 0
        conn.commit()
    return in_deleted, emb_deleted


def main() -> int:
    print("=== Daybook intent capture smoke test ===\n")

    pre_in, pre_em = _cleanup()
    if pre_in or pre_em:
        print(f"(pre-clean: removed {pre_in} intents + {pre_em} embeddings)\n")

    print("[Test 1] set_intent(text=...) — full pipeline")
    result = set_intent(user_id=DEFAULT_USER_ID, text=TEST_INTENT)
    print(f"  intent_id:    {result['intent_id']}")
    print(f"  embedding_id: {result['embedding_id']}")
    print(f"  set_at:       {result['set_at'].isoformat()}")
    print(f"  text:         {result['text']!r}")
    if result["embed_error"]:
        print(f"  embed_error:  {result['embed_error']}")

    assert result["intent_id"], "intent_id missing"
    assert _count_intents(result["intent_id"]) == 1, "intents row missing"
    print("  intents row:  present in DB")

    assert result["embedding_id"], "embedding_id missing"
    assert _count_embeddings(result["intent_id"]) == 1, "embeddings row missing"
    print("  embeddings:   present in DB (source_type='intent')")

    print("\n[Test 2] retrieve_similar finds the stored intent")
    hits = retrieve_similar(
        "colors lighthouse",
        user_id=DEFAULT_USER_ID,
        top_k=5,
        source_types=["intent"],
    )
    print(f"  got {len(hits)} hits")
    found = any(h.source_id == result["intent_id"] for h in hits)
    for h in hits[:5]:
        marker = " <-- our intent" if h.source_id == result["intent_id"] else ""
        print(f"   sim={h.similarity:.3f}  {h.source_id}{marker}")
    assert found, "retrieve_similar did not return our intent in top 5"
    print("  found our intent in top-5: OK")

    print("\n[Test 3] validation: empty text raises")
    try:
        set_intent(user_id=DEFAULT_USER_ID, text="   ")
    except ValueError as e:
        print(f"  raised as expected: {e}")
    else:
        raise AssertionError("set_intent should raise on empty text")

    print("\n[cleanup] Removing SMOKE_TEST: rows")
    in_deleted, em_deleted = _cleanup()
    print(f"  deleted {in_deleted} intents and {em_deleted} embeddings")

    print("\n=== Smoke test complete (all assertions passed) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
