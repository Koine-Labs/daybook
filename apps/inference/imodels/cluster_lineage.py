"""Cluster lineage tracking — record how new clusters relate to old ones.

When the nightly clusterer (re-)discovers a centroid sufficiently similar
(cosine > LINEAGE_SIMILARITY_THRESHOLD) to an existing cluster, instead of
silently overwriting yesterday's shape we record the relationship in
``i_model_cluster_lineage``. This is what lets Regis say "this looks like
what was going on with you in March" — the prior cluster is preserved
(dormant), and the child explicitly points back to it.

Relations:
  - 'supersedes'   : the child replaces the parent (parent flipped dormant)
  - 'merged_into'  : multiple parents collapsed into a single child
  - 'split_from'   : a single parent fanned out into multiple children
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402

logger = logging.getLogger(__name__)

# Module-level knob: cosine similarity above this between a new cluster's
# centroid and an existing one's centroid is treated as "the new one
# supersedes the old one" rather than "this is a fresh discovery".
#
# Why 0.65 (not 0.85): the clusterer's MERGE_SIMILARITY is 0.85 — anything
# at or above that gets merged in-place and never reaches lineage logic.
# So the lineage detector only ever sees centroids that landed below 0.85.
# Keeping this threshold at 0.85 too created a dead band [0.7, 0.85) where
# a new cluster was clearly evolved from a parent but no lineage row was
# written — silent loss of history. 0.65 captures "same region of
# mind-space" (drift, evolution) without being so loose that genuinely
# unrelated centroids get glued together.
LINEAGE_SIMILARITY_THRESHOLD = 0.65

VALID_RELATIONS = {"supersedes", "merged_into", "split_from"}


def record_lineage(
    parent_cluster_id: str,
    child_cluster_id: str,
    relation: str,
    *,
    user_id: str | None = None,
    similarity: float | None = None,
    context: dict | None = None,
    conn=None,
) -> str:
    """Insert one i_model_cluster_lineage row. Returns the new row's id.

    If ``user_id`` is omitted, we look it up from the child cluster — the
    lineage row's user_id must always equal both parent.user_id and
    child.user_id, but in practice the caller already knows the user.

    If ``conn`` is provided, the insert runs on that connection without
    committing (caller controls the transaction). Otherwise a fresh pooled
    connection is opened and committed on exit — preserving standalone
    callability for any other caller.
    """
    if relation not in VALID_RELATIONS:
        raise ValueError(
            f"relation must be one of {sorted(VALID_RELATIONS)}, got {relation!r}"
        )

    if conn is not None:
        lineage_id = _do_record_lineage(
            conn,
            parent_cluster_id=parent_cluster_id,
            child_cluster_id=child_cluster_id,
            relation=relation,
            user_id=user_id,
            similarity=similarity,
            context=context,
        )
    else:
        with get_conn() as own_conn:
            lineage_id = _do_record_lineage(
                own_conn,
                parent_cluster_id=parent_cluster_id,
                child_cluster_id=child_cluster_id,
                relation=relation,
                user_id=user_id,
                similarity=similarity,
                context=context,
            )
            own_conn.commit()

    logger.info(
        "lineage recorded id=%s parent=%s child=%s relation=%s sim=%s",
        lineage_id,
        parent_cluster_id,
        child_cluster_id,
        relation,
        f"{similarity:.4f}" if similarity is not None else "n/a",
    )
    return lineage_id


def _do_record_lineage(
    conn,
    *,
    parent_cluster_id: str,
    child_cluster_id: str,
    relation: str,
    user_id: str | None,
    similarity: float | None,
    context: dict | None,
) -> str:
    """Run the actual INSERT on the given connection. No commit."""
    with conn.cursor() as cur:
        if user_id is None:
            cur.execute(
                "SELECT user_id::text FROM i_model_clusters WHERE id = %s",
                (child_cluster_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"child cluster {child_cluster_id} not found")
            user_id = row[0]

        cur.execute(
            """
            INSERT INTO i_model_cluster_lineage
                (user_id, parent_cluster_id, child_cluster_id,
                 relation, similarity, context)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id::text
            """,
            (
                user_id,
                parent_cluster_id,
                child_cluster_id,
                relation,
                similarity,
                json.dumps(context or {}, default=str),
            ),
        )
        return cur.fetchone()[0]


def detect_and_record_supersessions(
    user_id: str,
    new_cluster_ids: list[str],
    existing_cluster_ids: list[str],
    *,
    similarity_threshold: float = LINEAGE_SIMILARITY_THRESHOLD,
) -> int:
    """Walk new clusters; record 'supersedes' rows for any that look like rebirths.

    For each new cluster, compare its centroid to every cluster in
    ``existing_cluster_ids`` (those that existed before this clustering run).
    If cosine similarity exceeds ``similarity_threshold``, record a
    'supersedes' lineage row pointing from the existing cluster (parent) to
    the new cluster (child), and mark the existing cluster dormant.

    The new cluster is also stamped ``last_activated_at = now()`` so the
    dormancy sweep won't immediately reverse the relationship.

    Returns the number of lineage rows written.
    """
    if not new_cluster_ids or not existing_cluster_ids:
        return 0

    new_centroids = _fetch_centroids(new_cluster_ids)
    existing_centroids = _fetch_centroids(existing_cluster_ids)
    if not new_centroids or not existing_centroids:
        return 0

    rows_written = 0
    for child_id, child_vec in new_centroids.items():
        best_parent: str | None = None
        best_sim = -1.0
        for parent_id, parent_vec in existing_centroids.items():
            if parent_id == child_id:
                continue
            sim = float(np.dot(child_vec, parent_vec))
            if sim > best_sim:
                best_sim, best_parent = sim, parent_id

        if best_parent is None or best_sim < similarity_threshold:
            continue

        # All three writes (lineage row, parent→dormant, child→active stamp)
        # happen in ONE transaction per supersession event. Prior design used
        # three separate pooled connections, so a process crash between any
        # two left a lineage row pointing to a parent that wasn't marked
        # dormant — silent inconsistency painful to debug later. Single
        # `with get_conn()` block + single commit at the end → atomic.
        try:
            with get_conn() as conn:
                _do_record_lineage(
                    conn,
                    parent_cluster_id=best_parent,
                    child_cluster_id=child_id,
                    relation="supersedes",
                    user_id=user_id,
                    similarity=best_sim,
                    context={
                        "detected_by": "clusterer",
                        "threshold": similarity_threshold,
                    },
                )
                _mark_dormant(best_parent, conn=conn)
                _stamp_active(child_id, conn=conn)
                conn.commit()
            logger.info(
                "supersession atomic-committed child=%s parent=%s sim=%.4f",
                child_id,
                best_parent,
                best_sim,
            )
            rows_written += 1
        except Exception as e:
            logger.warning(
                "detect_and_record_supersessions: failed for child=%s parent=%s: %s "
                "(transaction rolled back atomically)",
                child_id,
                best_parent,
                e,
            )

    return rows_written


def _fetch_centroids(cluster_ids: list[str]) -> dict[str, np.ndarray]:
    """Return {cluster_id: l2-normalized centroid} for the given ids."""
    if not cluster_ids:
        return {}
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, centroid_embedding::text
              FROM i_model_clusters
             WHERE id = ANY(%s::uuid[])
               AND centroid_embedding IS NOT NULL
            """,
            (cluster_ids,),
        )
        rows = cur.fetchall()
    out: dict[str, np.ndarray] = {}
    for cid, vec_text in rows:
        vec = np.array(_parse_vec(vec_text), dtype=np.float32)
        out[cid] = _l2_normalize(vec)
    return out


def _mark_dormant(cluster_id: str, *, conn=None) -> None:
    """Flip a cluster's status to 'dormant'.

    If ``conn`` is provided, runs on that connection without committing
    (caller controls the transaction). Otherwise opens + commits its own.
    """
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE i_model_clusters SET status = 'dormant' WHERE id = %s",
                (cluster_id,),
            )
        return
    with get_conn() as own_conn, own_conn.cursor() as cur:
        cur.execute(
            "UPDATE i_model_clusters SET status = 'dormant' WHERE id = %s",
            (cluster_id,),
        )
        own_conn.commit()


def _stamp_active(cluster_id: str, *, conn=None) -> None:
    """Mark a cluster active and bump last_activated_at to now().

    If ``conn`` is provided, runs on that connection without committing
    (caller controls the transaction). Otherwise opens + commits its own.
    """
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE i_model_clusters
                   SET status = 'active', last_activated_at = now()
                 WHERE id = %s
                """,
                (cluster_id,),
            )
        return
    with get_conn() as own_conn, own_conn.cursor() as cur:
        cur.execute(
            """
            UPDATE i_model_clusters
               SET status = 'active', last_activated_at = now()
             WHERE id = %s
            """,
            (cluster_id,),
        )
        own_conn.commit()


def _parse_vec(vec_text: str) -> list[float]:
    return [float(x) for x in vec_text.strip("[]").split(",")]


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        return vec
    return vec / norm


__all__ = [
    "LINEAGE_SIMILARITY_THRESHOLD",
    "VALID_RELATIONS",
    "detect_and_record_supersessions",
    "record_lineage",
]
