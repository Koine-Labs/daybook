"""End-to-end smoke test for the I-Model self-expansion machinery.

Seeds ~30 synthetic embeddings into 3 thematic groups, runs the clusterer,
exercises the activator and novelty detector, then cleans up all test rows.

Run with:
    cd apps/inference && source .venv/bin/activate
    python -m imodels.smoke_test
"""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_conn  # noqa: E402
from embeddings import embed_batch, embed  # noqa: E402
from embeddings.store import store_embedding  # noqa: E402

from .activator import get_active_clusters
from .clusterer import run_clusterer
from .novelty import flag_for_reclustering, log_novelty_observation

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
SMOKE_SOURCE_TYPE = "imodel_smoke"

# Three thematic clusters — small variations within each to test cohesion.
SEED_TEXTS = [
    # Cluster A — underwater / drowning theme
    "Underwater in a vast ocean. The water pressed against my chest.",
    "Diving deep. Couldn't breathe but didn't panic.",
    "Swimming below the surface. The light filtered down from above.",
    "Trapped in a flooded room. Water rising around me.",
    "Floating in cold dark water. Currents pulling me deeper.",
    "Submerged in a green lake. Fish brushing against me.",
    "Drowning slowly in a swimming pool. No one saw.",
    "Pulled under by a wave. Salt water in my throat.",
    "Tank of water enclosing me. Could see out but not escape.",
    "Sinking into murky depths. Reaching for sunlight.",
    # Cluster B — family / grandfather theme
    "My grandfather sitting at the dinner table. He couldn't see me.",
    "Visiting my grandparents' old house. Everything frozen in time.",
    "Walking with my grandfather through fields. He was younger.",
    "My mother in the kitchen humming an old song.",
    "Family reunion in the backyard. Lights strung overhead.",
    "Sitting with my father in his garage. Smell of motor oil.",
    "Grandfather telling me a story I'd never heard before.",
    "Grandmother handing me a worn photograph of strangers.",
    "Holiday dinner with my family. Empty chair at the end.",
    "Grandfather's grave overgrown with wildflowers I planted.",
    # Cluster C — work / building / coding theme
    "Coding through the night. The screen flickered like fire.",
    "Building a complex machine in my workshop. Sparks flew.",
    "Writing software that wouldn't compile. Errors kept multiplying.",
    "Soldering circuit boards under harsh fluorescent light.",
    "Designing a system architecture. Lines connecting nowhere.",
    "Working on a Pi project. Wires tangled around everything.",
    "Debugging an impossible race condition. Tests kept failing.",
    "Programming firmware for a strange new device.",
    "Wiring up sensors to an ESP32. Tape on every connection.",
    "Crafting an algorithm in my head while walking.",
]


def _seed_embeddings() -> tuple[list[str], list[str], list[str]]:
    """Embed and store seed texts. Returns (embedding_ids, source_ids, texts)."""
    print(f"  Embedding {len(SEED_TEXTS)} seed texts (may take ~5-10s)...")
    vectors = embed_batch(SEED_TEXTS)
    embedding_ids: list[str] = []
    source_ids: list[str] = []
    for text, vec in zip(SEED_TEXTS, vectors):
        sid = str(uuid4())
        eid = store_embedding(
            user_id=DEFAULT_USER_ID,
            source_type=SMOKE_SOURCE_TYPE,
            source_id=sid,
            vector=vec,
        )
        embedding_ids.append(eid)
        source_ids.append(sid)
    print(f"  Stored {len(embedding_ids)} embeddings.")
    return embedding_ids, source_ids, SEED_TEXTS


def _cleanup(embedding_ids: list[str]) -> dict[str, int]:
    """Remove smoke test rows. Returns counts of deletions."""
    counts = {}
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM embedding_cluster_memberships WHERE embedding_id = ANY(%s)",
            (embedding_ids,),
        )
        counts["memberships"] = cur.rowcount

        # Find clusters that were created by this smoke test (have ONLY smoke-test members
        # — easiest heuristic: pick clusters whose model_owner='user_self' and have NO remaining
        # memberships after the delete above).
        cur.execute(
            """
            DELETE FROM i_model_clusters c
            WHERE c.user_id = %s
              AND c.model_owner = 'user_self'
              AND NOT EXISTS (
                SELECT 1 FROM embedding_cluster_memberships m
                WHERE m.cluster_id = c.id
              )
              AND c.label IS NULL
              AND c.discovered_at > NOW() - INTERVAL '10 minutes'
            """,
            (DEFAULT_USER_ID,),
        )
        counts["clusters"] = cur.rowcount

        cur.execute(
            "DELETE FROM i_model_novelty_log WHERE user_id = %s AND observed_at > NOW() - INTERVAL '10 minutes'",
            (DEFAULT_USER_ID,),
        )
        counts["novelty"] = cur.rowcount

        cur.execute(
            "DELETE FROM i_model_activations WHERE source = 'activator_job' AND activated_at > NOW() - INTERVAL '10 minutes'",
            (),
        )
        counts["activations"] = cur.rowcount

        cur.execute(
            "DELETE FROM embeddings WHERE id = ANY(%s)",
            (embedding_ids,),
        )
        counts["embeddings"] = cur.rowcount
        conn.commit()
    return counts


def main() -> int:
    print("=== Daybook I-Models smoke test ===\n")

    print("[1] Seeding 30 synthetic embeddings (3 themes)...")
    embedding_ids, _source_ids, _texts = _seed_embeddings()

    try:
        print("\n[2] Running clusterer (source_types=['imodel_smoke'], min_cluster_size=3)...")
        summary = run_clusterer(
            DEFAULT_USER_ID,
            model_owner="user_self",
            source_types=[SMOKE_SOURCE_TYPE],
            min_cluster_size=3,
            min_embeddings=10,
        )
        print(f"  Result: {summary}")
        assert summary.get("discovered", 0) + summary.get("updated", 0) > 0, (
            "Clusterer did not discover any clusters — investigate."
        )

        print("\n[3] Running activator on a 'water' query...")
        active = get_active_clusters(
            user_id=DEFAULT_USER_ID,
            query_text="I was deep in water and could not breathe",
            top_k=3,
            min_similarity=0.2,
            persist=True,
        )
        for c in active:
            print(
                f"  cluster_id={c.cluster_id[:8]}.. label={c.label} owner={c.model_owner} sim={c.similarity:.3f}"
            )
        assert active, "Activator returned 0 results"
        assert active[0].similarity > 0.4, (
            f"Top water-query similarity should be > 0.4, got {active[0].similarity:.3f}"
        )

        print("\n[4] Running activator on a 'grandfather' query...")
        active2 = get_active_clusters(
            user_id=DEFAULT_USER_ID,
            query_text="My grandfather and I in the kitchen",
            top_k=3,
            min_similarity=0.2,
        )
        for c in active2:
            print(
                f"  cluster_id={c.cluster_id[:8]}.. label={c.label} owner={c.model_owner} sim={c.similarity:.3f}"
            )

        print("\n[5] Novelty detection — a totally unrelated state...")
        novel_vec = embed("I was walking on Mars among red dust and broken glass towers.")
        novel = log_novelty_observation(
            user_id=DEFAULT_USER_ID,
            state_snapshot={"smoke_test": True, "reason": "Mars vignette"},
            embedding=novel_vec,
            novelty_threshold=0.7,
        )
        print(f"  Result: {novel}")
        assert novel["logged"] is True, "Mars vignette should be flagged as novel at threshold 0.7"

        print("\n[6] Novelty detection — a state similar to an existing cluster (should NOT log)...")
        similar_vec = embed("Submerged in dark water, lungs aching for air.")
        sim_result = log_novelty_observation(
            user_id=DEFAULT_USER_ID,
            state_snapshot={"smoke_test": True, "reason": "in-cluster"},
            embedding=similar_vec,
            novelty_threshold=0.4,
        )
        print(f"  Result: {sim_result}")
        assert not sim_result["logged"], "Similar state should not be logged as novel"

        print("\n[7] flag_for_reclustering (need 1 novelty entry to flag, low threshold)...")
        flagged = flag_for_reclustering(DEFAULT_USER_ID, min_novelty_count=1)
        print(f"  Flagged {flagged} novelty entries for reclustering")

    finally:
        print("\n[8] Cleaning up smoke test rows...")
        counts = _cleanup(embedding_ids)
        for k, v in counts.items():
            print(f"  deleted {v} from {k}")

    print("\n=== I-Models smoke test complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
