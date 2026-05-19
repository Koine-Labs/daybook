"""Novelty buffer: log observations that don't fit existing I-Model clusters.

When the current state's best similarity to any cluster is below a threshold,
write it to i_model_novelty_log. Once enough novel entries accumulate they get
flagged for the next clustering pass — possibly crystallizing into a new
I-Model.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_conn  # noqa: E402

logger = logging.getLogger(__name__)

# Source types that are user-side evidence (per audit item #4 coverage decisions).
# regis_moment is excluded — Regis's own voice, not user-state.
USER_SIDE_SOURCE_TYPES = (
    "chat_message",      # user role only — filtered in backfill SQL
    "regis_observation",
    "dream_recall",
    "intent",
    "mood",
)

# BGE-M3 cosine floor is ~0.45 for unrelated text (gibberish, random noise);
# 0.55 captures genuinely-novel-for-this-user states while filtering out
# the natural similarity floor. The previous default (0.4) sat below the
# floor, so for any user with existing clusters is_novel=False ALWAYS and
# the novelty log stayed empty. Tune here, single source of truth.
DEFAULT_NOVELTY_THRESHOLD = 0.55


def log_novelty_observation(
    *,
    user_id: str,
    state_snapshot: dict[str, Any],
    embedding: list[float],
    novelty_threshold: float = DEFAULT_NOVELTY_THRESHOLD,
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
              AND model_owner <> 'regis_self'
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


def backfill_novelty_log(
    *,
    user_id: str,
    limit: int = 5000,
) -> dict[str, int]:
    """Catch-up: log novelty for existing user-side embeddings that have none.

    Walks the embeddings table for user_id, filters to user-side source_types
    (chat_message user-role rows, regis_observation, dream_recall, intent,
    mood), skips any source_id already present in i_model_novelty_log via the
    embedded state_snapshot.source_id, and calls log_novelty_observation on
    the rest. Returns counts: scanned, logged, skipped_not_novel, errors.
    """
    counts = {"scanned": 0, "logged": 0, "skipped_not_novel": 0, "errors": 0}

    # Build the set of source_ids already represented in the novelty log so
    # repeated backfills are idempotent. We compare via state_snapshot.source_id.
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT state_snapshot ->> 'source_id'
            FROM i_model_novelty_log
            WHERE user_id = %s
              AND state_snapshot ? 'source_id'
            """,
            (user_id,),
        )
        already_logged: set[str] = {r[0] for r in cur.fetchall() if r[0]}

    # Pull candidate embeddings.
    # For chat_message we restrict to role='user'; everything else accepts all rows.
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.id::text, e.source_type, e.source_id::text, e.embedding::text,
                   COALESCE(cm.role, '') AS chat_role,
                   COALESCE(ro.observation, dr.raw_text, i.intent_text,
                            mr.notes, '') AS preview_text,
                   COALESCE(cm.content, '') AS chat_content
            FROM embeddings e
            LEFT JOIN chat_messages cm
              ON e.source_type = 'chat_message' AND cm.id = e.source_id::uuid
            LEFT JOIN regis_observations ro
              ON e.source_type = 'regis_observation' AND ro.id = e.source_id::uuid
            LEFT JOIN dream_recalls dr
              ON e.source_type = 'dream_recall' AND dr.id = e.source_id::uuid
            LEFT JOIN intents i
              ON e.source_type = 'intent' AND i.id = e.source_id::uuid
            LEFT JOIN mood_reports mr
              ON e.source_type = 'mood' AND mr.id = e.source_id::uuid
            WHERE e.user_id = %s
              AND e.source_type = ANY(%s)
              AND (e.source_type <> 'chat_message' OR cm.role = 'user')
            ORDER BY e.created_at ASC
            LIMIT %s
            """,
            (user_id, list(USER_SIDE_SOURCE_TYPES), limit),
        )
        rows = cur.fetchall()

    for emb_id, source_type, source_id, emb_str, chat_role, preview, chat_content in rows:
        counts["scanned"] += 1
        if source_id in already_logged:
            continue
        try:
            # pgvector text format: "[v1,v2,...]"
            vec = [float(x) for x in emb_str.strip("[]").split(",")]
        except Exception as e:
            counts["errors"] += 1
            logger.warning("backfill: parse vec failed for %s: %s", emb_id, e)
            continue

        text_preview = (chat_content or preview or "")[:200]
        snapshot = {
            "source_type": source_type,
            "source_id": source_id,
            "embedding_id": emb_id,
            "text_preview": text_preview,
            "backfilled": True,
        }
        if source_type == "chat_message":
            snapshot["role"] = chat_role
        try:
            result = log_novelty_observation(
                user_id=user_id,
                state_snapshot=snapshot,
                embedding=vec,
            )
            if result.get("logged"):
                counts["logged"] += 1
                already_logged.add(source_id)
            else:
                counts["skipped_not_novel"] += 1
        except Exception as e:
            counts["errors"] += 1
            logger.warning("backfill: log_novelty failed for %s: %s", emb_id, e)
    return counts


def _main() -> int:
    ap = argparse.ArgumentParser(
        description="Novelty log utilities: backfill existing user-side embeddings."
    )
    ap.add_argument("--backfill", action="store_true", help="Run the backfill.")
    ap.add_argument(
        "--user-id",
        default="61c18d4c-1c20-408a-bd5f-f5f88fd9922f",
        help="User UUID (default: Aakash).",
    )
    ap.add_argument("--limit", type=int, default=5000)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.backfill:
        counts = backfill_novelty_log(user_id=args.user_id, limit=args.limit)
        print(
            f"Backfill: scanned={counts['scanned']} logged={counts['logged']} "
            f"skipped_not_novel={counts['skipped_not_novel']} errors={counts['errors']}"
        )
        return 0

    # Default: status — show how many rows exist + how many user-side embeddings
    # don't have a novelty entry yet.
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM i_model_novelty_log WHERE user_id = %s",
            (args.user_id,),
        )
        novelty_total = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM i_model_novelty_log "
            "WHERE user_id = %s AND clustered_into_id IS NULL "
            "AND flagged_for_clustering = FALSE",
            (args.user_id,),
        )
        unflagged = cur.fetchone()[0]
    print(f"novelty rows: {novelty_total}  unflagged: {unflagged}")
    print("Run with --backfill to catch up from existing embeddings.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
