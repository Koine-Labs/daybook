"""Smoke test: load BGE-M3, embed sample dream texts, write to DB, retrieve by similarity.

Run with:
    cd apps/inference && source .venv/bin/activate
    python -m embeddings.smoke_test
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_conn  # noqa: E402

from .model import EMBED_DIM, MODEL_NAME, embed, embed_batch, get_model
from .retrieve import retrieve_similar
from .store import embed_and_store

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"

SAMPLE_DREAMS = [
    "I was swimming in the ocean at night. The water was warm and full of pale fish.",
    "Standing in my grandfather's house. He was at the table but couldn't see me.",
    "Driving down a road I've never seen. The sky was orange and the trees were black.",
    "Underwater again, deeper this time. I could breathe but my chest hurt.",
    "At a wedding I wasn't invited to. Everyone was wearing white and ignoring me.",
    "Flying low over a mountain valley. I could feel the air pressure shift.",
    "My grandfather was sitting on a beach. The sea behind him was glowing.",
]


def main() -> int:
    print("=== Daybook embeddings smoke test ===\n")

    # 1. Load model
    print(f"Loading model {MODEL_NAME} (expect ~10-30s first time) ...")
    t0 = time.monotonic()
    model = get_model()
    dt = time.monotonic() - t0
    print(f"  Loaded in {dt:.1f}s. Embedding dim: {model.get_sentence_embedding_dimension()}")
    assert model.get_sentence_embedding_dimension() == EMBED_DIM, "Dim mismatch with schema!"

    # 2. Embed single text
    print("\n[1] embed() one dream:")
    t0 = time.monotonic()
    vec = embed(SAMPLE_DREAMS[0])
    dt = time.monotonic() - t0
    print(f"  text: {SAMPLE_DREAMS[0][:60]}...")
    print(f"  embedded in {dt*1000:.0f}ms, dim={len(vec)}, first 5: {[round(v,3) for v in vec[:5]]}")

    # 3. Batch embed
    print("\n[2] embed_batch() seven dreams:")
    t0 = time.monotonic()
    vecs = embed_batch(SAMPLE_DREAMS)
    dt = time.monotonic() - t0
    print(f"  {len(vecs)} embeddings in {dt*1000:.0f}ms total ({dt*1000/len(vecs):.0f}ms each)")

    # 4. Store to DB (with cleanup at end)
    print("\n[3] Write embeddings to DB (smoke-test tag, will clean up at end):")
    inserted_ids = []
    fake_source_ids = []
    for dream in SAMPLE_DREAMS:
        fake_sid = str(uuid4())
        fake_source_ids.append(fake_sid)
        eid, _vec = embed_and_store(
            user_id=DEFAULT_USER_ID,
            source_type="dream_recall_smoke",
            source_id=fake_sid,
            text=dream,
        )
        inserted_ids.append(eid)
    print(f"  Stored {len(inserted_ids)} embeddings to DB.")

    # 5. Retrieve by similarity — query about "water"
    print("\n[4] retrieve_similar() — query about water:")
    q = "I was deep in water and could breathe but felt my chest tighten."
    results = retrieve_similar(
        q,
        user_id=DEFAULT_USER_ID,
        top_k=5,
        source_types=["dream_recall_smoke"],
    )
    print(f"  Query: {q}")
    for r in results:
        # Map back from fake source_id to original dream text
        idx = fake_source_ids.index(r.source_id) if r.source_id in fake_source_ids else -1
        dream_text = SAMPLE_DREAMS[idx] if idx >= 0 else "(unknown)"
        print(f"  {r.similarity:.3f}  {dream_text[:70]}")

    # 6. Retrieve about "grandfather"
    print("\n[5] retrieve_similar() — query about grandfather:")
    q2 = "An old man, my grandfather, near water."
    results2 = retrieve_similar(
        q2,
        user_id=DEFAULT_USER_ID,
        top_k=3,
        source_types=["dream_recall_smoke"],
    )
    print(f"  Query: {q2}")
    for r in results2:
        idx = fake_source_ids.index(r.source_id) if r.source_id in fake_source_ids else -1
        dream_text = SAMPLE_DREAMS[idx] if idx >= 0 else "(unknown)"
        print(f"  {r.similarity:.3f}  {dream_text[:70]}")

    # 7. Cleanup
    print("\n[6] Cleaning up smoke-test rows...")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM embeddings WHERE source_type = %s",
            ("dream_recall_smoke",),
        )
        deleted = cur.rowcount
        conn.commit()
    print(f"  Deleted {deleted} smoke-test rows.")

    print("\n=== Smoke test complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
