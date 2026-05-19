"""Find which I-Model clusters are "active" right now given a query vector.

Called at decision time by the chat composer / wisp composer to bias retrieval
by the user's currently-firing modes (e.g., "Aakash is in builder mode" vs
"Aakash is in reflective mode" — both could be active simultaneously).
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_conn  # noqa: E402
from embeddings import embed  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass
class ActiveCluster:
    cluster_id: str
    label: str | None
    similarity: float
    model_owner: str


def get_active_clusters(
    *,
    user_id: str,
    query_embedding: list[float] | None = None,
    query_text: str | None = None,
    model_owners: Sequence[str] = ("user_self", "regis_of_user"),
    top_k: int = 3,
    min_similarity: float = 0.4,
    persist: bool = False,
) -> list[ActiveCluster]:
    """Return top_k clusters most similar to query, across the requested model_owners.

    One of query_embedding or query_text is required. If persist=True, an
    i_model_activations row is written per returned cluster.
    """
    if query_embedding is None and not query_text:
        raise ValueError("Must provide query_embedding or query_text")

    qvec = query_embedding if query_embedding is not None else embed(query_text)
    qvec_literal = _vec_literal(qvec)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, label, model_owner,
                   1 - (centroid_embedding <=> %s::vector) AS sim
            FROM i_model_clusters
            WHERE user_id = %s
              AND model_owner = ANY(%s)
              AND centroid_embedding IS NOT NULL
              AND status = 'active'
            ORDER BY centroid_embedding <=> %s::vector ASC
            LIMIT %s
            """,
            (qvec_literal, user_id, list(model_owners), qvec_literal, top_k * 4),
        )
        rows = cur.fetchall()

    results = [
        ActiveCluster(
            cluster_id=r[0],
            label=r[1],
            similarity=float(r[3]),
            model_owner=r[2],
        )
        for r in rows
        if float(r[3]) >= min_similarity
    ][:top_k]

    if results:
        try:
            _stamp_activation_timestamps([c.cluster_id for c in results])
        except Exception as e:
            logger.warning("activator timestamp-stamp failed: %s", e)

    if persist and results:
        try:
            _persist_activations(results, context={"query_text": query_text})
        except Exception as e:
            logger.warning("activator persist failed: %s", e)

    return results


def _stamp_activation_timestamps(cluster_ids: list[str]) -> None:
    """Batched UPDATE: bump last_activated_at = now() for each cluster.

    Cluster dormancy depends on this — clusters that fire stay active.
    """
    if not cluster_ids:
        return
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE i_model_clusters
               SET last_activated_at = now()
             WHERE id = ANY(%s::uuid[])
            """,
            (cluster_ids,),
        )
        conn.commit()


def _persist_activations(active: list[ActiveCluster], *, context: dict) -> None:
    """Write i_model_activations rows for each active cluster."""
    with get_conn() as conn, conn.cursor() as cur:
        for c in active:
            cur.execute(
                """
                INSERT INTO i_model_activations
                    (cluster_id, activation_strength, source, context)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (c.cluster_id, _clamp01(c.similarity), "activator_job", json.dumps(context, default=str)),
            )
        conn.commit()


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
