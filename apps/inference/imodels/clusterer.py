"""HDBSCAN-based discovery of I-Model clusters from accumulated embeddings.

The job pulls embeddings for a (user, model_owner) scope, clusters them, then
compares discovered cluster centroids to any existing clusters for that owner.
Each discovered cluster either:
  - Matches an existing one (cosine sim > MERGE_SIMILARITY) and is merged in
  - Or is registered as a new (unlabeled) i_model_clusters row

Membership rows in embedding_cluster_memberships record the many-to-many link
per Aakash's "neurons fire across multiple I-Models" insight.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_conn  # noqa: E402

logger = logging.getLogger(__name__)

# When a discovered cluster centroid is at least this similar to an existing
# cluster centroid (cosine), we update the existing one rather than minting a new row.
MERGE_SIMILARITY = 0.85

# Default source_types per model owner.
DEFAULT_SOURCE_TYPES: dict[str, list[str]] = {
    "user_self": ["dream_recall", "intent", "mood"],
    "regis_of_user": ["regis_observation"],
    "regis_self": [],
}


def run_clusterer(
    user_id: str,
    *,
    model_owner: str = "user_self",
    source_types: list[str] | None = None,
    min_cluster_size: int = 5,
    min_embeddings: int = 20,
    dry_run: bool = False,
) -> dict:
    """Run HDBSCAN clustering on accumulated embeddings.

    Steps:
      1. Pull embeddings for this user filtered by source_types.
      2. If fewer than min_embeddings, abort with reason.
      3. Cluster via HDBSCAN (fallback DBSCAN); skip noise points.
      4. For each discovered cluster, compute its centroid (mean of normalized
         vectors), then compare to existing cluster centroids for this
         (user, model_owner) — merge if cosine similarity > MERGE_SIMILARITY,
         else create a new unlabeled cluster row.
      5. Write/refresh embedding_cluster_memberships for cluster members.

    Returns a summary dict.
    """
    if model_owner == "regis_self":
        return {
            "skipped": True,
            "reason": "regis_self uses regis_trait_history, not clustering",
        }

    if source_types is None:
        source_types = DEFAULT_SOURCE_TYPES.get(model_owner, [])
    if not source_types:
        return {"skipped": True, "reason": f"no default source_types for {model_owner}"}

    rows = _fetch_embeddings(user_id=user_id, source_types=source_types)
    if len(rows) < min_embeddings:
        logger.info(
            "insufficient_data user=%s owner=%s have=%d need=%d",
            user_id,
            model_owner,
            len(rows),
            min_embeddings,
        )
        return {
            "skipped": True,
            "reason": "insufficient_data",
            "have": len(rows),
            "need": min_embeddings,
        }

    embedding_ids = [r[0] for r in rows]
    vectors = np.array([r[1] for r in rows], dtype=np.float32)

    labels = _cluster(vectors, min_cluster_size=min_cluster_size)
    unique_clusters = sorted({int(l) for l in labels if l >= 0})
    if not unique_clusters:
        return {
            "discovered": 0,
            "updated": 0,
            "total_embeddings_clustered": 0,
            "noise_points": int(np.sum(labels == -1)),
            "input_embeddings": len(rows),
        }

    existing = _fetch_existing_clusters(user_id=user_id, model_owner=model_owner)

    discovered = 0
    updated = 0
    memberships: list[tuple[str, str, float]] = []  # (embedding_id, cluster_id, sim)

    for cluster_label in unique_clusters:
        member_mask = labels == cluster_label
        member_vecs = vectors[member_mask]
        member_emb_ids = [embedding_ids[i] for i, m in enumerate(member_mask) if m]
        centroid = _l2_normalize(member_vecs.mean(axis=0))

        target_cluster_id, was_merge = _resolve_target_cluster(
            centroid=centroid,
            existing=existing,
            user_id=user_id,
            model_owner=model_owner,
            dry_run=dry_run,
        )

        if was_merge:
            updated += 1
        else:
            discovered += 1
            if not dry_run:
                existing[target_cluster_id] = centroid

        for eid, vec in zip(member_emb_ids, member_vecs):
            sim = float(np.dot(_l2_normalize(vec), centroid))
            memberships.append((eid, target_cluster_id, sim))

    if not dry_run and memberships:
        _upsert_memberships(memberships)

    return {
        "discovered": discovered,
        "updated": updated,
        "total_embeddings_clustered": len(memberships),
        "noise_points": int(np.sum(labels == -1)),
        "input_embeddings": len(rows),
        "dry_run": dry_run,
    }


def _cluster(vectors: np.ndarray, *, min_cluster_size: int) -> np.ndarray:
    """Try HDBSCAN first, fallback to DBSCAN. Returns label-per-vector."""
    try:
        import hdbscan

        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric="euclidean",  # BGE-M3 vectors are L2-normalized → euclidean ~= cosine
        )
        return clusterer.fit_predict(vectors)
    except Exception as e:
        logger.warning("hdbscan failed (%s); falling back to DBSCAN", e)
        from sklearn.cluster import DBSCAN

        return DBSCAN(eps=0.5, min_samples=min_cluster_size, metric="euclidean").fit_predict(
            vectors
        )


def _resolve_target_cluster(
    *,
    centroid: np.ndarray,
    existing: dict[str, np.ndarray],
    user_id: str,
    model_owner: str,
    dry_run: bool,
) -> tuple[str, bool]:
    """Find a similar existing cluster to merge into; else create new. Returns (id, was_merge)."""
    best_id: str | None = None
    best_sim = -1.0
    for cid, c in existing.items():
        sim = float(np.dot(centroid, c))
        if sim > best_sim:
            best_sim, best_id = sim, cid

    if best_id is not None and best_sim >= MERGE_SIMILARITY:
        if not dry_run:
            _update_cluster_centroid(best_id, centroid)
        return best_id, True

    if dry_run:
        from uuid import uuid4

        return f"dry-{uuid4()}", False
    new_id = _insert_cluster(user_id=user_id, model_owner=model_owner, centroid=centroid)
    return new_id, False


def _fetch_embeddings(*, user_id: str, source_types: list[str]) -> list[tuple[str, list[float]]]:
    """Pull embedding rows for the (user, source_types) scope."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, embedding::text
            FROM embeddings
            WHERE user_id = %s AND source_type = ANY(%s)
            """,
            (user_id, source_types),
        )
        rows = cur.fetchall()
    return [(r[0], _parse_vec(r[1])) for r in rows]


def _fetch_existing_clusters(
    *, user_id: str, model_owner: str
) -> dict[str, np.ndarray]:
    """Map cluster_id -> centroid (only those with non-null centroids)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, centroid_embedding::text
            FROM i_model_clusters
            WHERE user_id = %s AND model_owner = %s
              AND centroid_embedding IS NOT NULL
            """,
            (user_id, model_owner),
        )
        rows = cur.fetchall()
    return {r[0]: _l2_normalize(np.array(_parse_vec(r[1]), dtype=np.float32)) for r in rows}


def _insert_cluster(*, user_id: str, model_owner: str, centroid: np.ndarray) -> str:
    """Create a new unlabeled cluster row. Returns its id."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO i_model_clusters
                (user_id, model_owner, label, centroid_embedding)
            VALUES (%s, %s, NULL, %s::vector)
            RETURNING id::text
            """,
            (user_id, model_owner, _vec_literal(centroid.tolist())),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
    return new_id


def _update_cluster_centroid(cluster_id: str, centroid: np.ndarray) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE i_model_clusters SET centroid_embedding = %s::vector WHERE id = %s",
            (_vec_literal(centroid.tolist()), cluster_id),
        )
        conn.commit()


def _upsert_memberships(memberships: list[tuple[str, str, float]]) -> None:
    """Insert-or-update embedding_cluster_memberships rows in a single batch.

    Uses psycopg3's executemany (extended-protocol pipelined) so a 1000-member
    cluster is one round-trip instead of 1000. ON CONFLICT semantics preserved
    exactly — same SQL, just one batched send.
    """
    if not memberships:
        return
    with get_conn() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO embedding_cluster_memberships
                (embedding_id, cluster_id, similarity, assignment_source)
            VALUES (%s, %s, %s, 'clusterer')
            ON CONFLICT (embedding_id, cluster_id) DO UPDATE
              SET similarity = EXCLUDED.similarity,
                  assigned_at = NOW()
            """,
            memberships,
        )
        conn.commit()


def _parse_vec(vec_text: str) -> list[float]:
    """pgvector text form '[1.0,2.0,...]' -> list[float]."""
    return [float(x) for x in vec_text.strip("[]").split(",")]


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        return vec
    return vec / norm


def _main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", required=True)
    ap.add_argument(
        "--model-owner",
        default="user_self",
        choices=["user_self", "regis_of_user", "regis_self"],
    )
    ap.add_argument("--source-types", nargs="*", default=None)
    ap.add_argument("--min-cluster-size", type=int, default=5)
    ap.add_argument("--min-embeddings", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    summary = run_clusterer(
        args.user_id,
        model_owner=args.model_owner,
        source_types=args.source_types,
        min_cluster_size=args.min_cluster_size,
        min_embeddings=args.min_embeddings,
        dry_run=args.dry_run,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
