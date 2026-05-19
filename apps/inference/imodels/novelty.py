"""Novelty buffer: log observations that don't fit existing I-Model clusters.

When the current state's best similarity to any cluster is below a threshold,
write it to i_model_novelty_log. Once enough novel entries accumulate they get
flagged for the next clustering pass — possibly crystallizing into a new
I-Model.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_conn  # noqa: E402

logger = logging.getLogger(__name__)


def log_novelty_observation(
    *,
    user_id: str,
    state_snapshot: dict[str, Any],
    embedding: list[float],
    novelty_threshold: float = 0.4,
) -> dict:
    """Compare state to existing clusters; log if novel. Returns a summary dict."""
    qvec_literal = _vec_literal(embedding)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, 1 - (centroid_embedding <=> %s::vector) AS sim
            FROM i_model_clusters
            WHERE user_id = %s
              AND centroid_embedding IS NOT NULL
              AND status = 'active'
            ORDER BY centroid_embedding <=> %s::vector ASC
            LIMIT 1
            """,
            (qvec_literal, user_id, qvec_literal),
        )
        row = cur.fetchone()

    if row is None:
        nearest_id, nearest_sim = None, None
        is_novel = True
    else:
        nearest_id, nearest_sim = row[0], float(row[1])
        is_novel = nearest_sim < novelty_threshold

    if not is_novel:
        return {
            "logged": False,
            "nearest_cluster_id": nearest_id,
            "nearest_similarity": nearest_sim,
            "is_novel": False,
        }

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO i_model_novelty_log
                    (user_id, state_snapshot, embedding,
                     nearest_cluster_id, nearest_similarity)
                VALUES (%s, %s::jsonb, %s::vector, %s, %s)
                RETURNING id::text
                """,
                (
                    user_id,
                    json.dumps(state_snapshot, default=str),
                    qvec_literal,
                    nearest_id,
                    nearest_sim,
                ),
            )
            new_id = cur.fetchone()[0]
            conn.commit()
    except Exception as e:
        logger.warning("novelty persist failed: %s", e)
        return {
            "logged": False,
            "nearest_cluster_id": nearest_id,
            "nearest_similarity": nearest_sim,
            "is_novel": True,
            "error": str(e),
        }

    return {
        "logged": True,
        "novelty_log_id": new_id,
        "nearest_cluster_id": nearest_id,
        "nearest_similarity": nearest_sim,
        "is_novel": True,
    }


def flag_for_reclustering(user_id: str, min_novelty_count: int = 10) -> int:
    """If user has min_novelty_count+ unclustered novel entries, flag them.

    Returns count of rows newly flagged.
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM i_model_novelty_log
            WHERE user_id = %s
              AND clustered_into_id IS NULL
              AND flagged_for_clustering = FALSE
            """,
            (user_id,),
        )
        unflagged = int(cur.fetchone()[0])

        if unflagged < min_novelty_count:
            return 0

        cur.execute(
            """
            UPDATE i_model_novelty_log
            SET flagged_for_clustering = TRUE
            WHERE user_id = %s
              AND clustered_into_id IS NULL
              AND flagged_for_clustering = FALSE
            """,
            (user_id,),
        )
        flagged = cur.rowcount
        conn.commit()
    return flagged


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
