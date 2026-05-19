"""Embed Regis's own utterances into the embeddings table.

Closes the asymmetry described in audit item #12: chat_messages,
regis_observations, dream_recalls, intents, and mood_reports all get embedded
when persisted, but regis_moments (what Regis says proactively) did not. As a
result Regis could recall what the user said but forgot what he himself had
said.

Public surface:
  embed_regis_moment(user_id, moment_id, content)     -> str | None
      Fire-and-forget hook called from every regis_moments insert site,
      immediately after the commit. Logs and swallows errors — embedding
      failure must NEVER break the moment-write path.

  backfill_regis_moment_embeddings(user_id, limit)   -> int
      One-shot catch-up for existing regis_moments rows that have no
      corresponding embeddings row. Returns the number of rows embedded.

The source_type string is **'regis_moment'** (singular) to match the existing
convention in the embeddings table ('chat_message', 'regis_observation',
'dream_recall', 'intent').
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Path setup so we can import from apps/inference/
INFERENCE_DIR = Path(__file__).resolve().parent.parent / "inference"
sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402
from embeddings import embed_and_store  # noqa: E402

REGIS_MOMENT_SOURCE_TYPE = "regis_moment"

logger = logging.getLogger(__name__)


def embed_regis_moment(
    user_id: str,
    moment_id: str,
    content: str,
) -> str | None:
    """Embed one regis_moments row into the embeddings table.

    Returns the new embedding id on success, or None on failure.
    Failures are logged but never raised — this is a non-critical hook
    and must not break the caller's moment-write path.
    """
    if not content or not content.strip():
        logger.debug("embed_regis_moment: empty content for moment %s, skipping", moment_id)
        return None
    try:
        emb_id, _vec = embed_and_store(
            user_id=user_id,
            source_type=REGIS_MOMENT_SOURCE_TYPE,
            source_id=moment_id,
            text=content,
        )
        return emb_id
    except Exception as e:  # noqa: BLE001 — intentional broad catch
        logger.warning(
            "embed_regis_moment: failed to embed moment %s for user %s: %s",
            moment_id, user_id, e,
        )
        return None


def backfill_regis_moment_embeddings(
    user_id: str | None = None,
    limit: int = 1000,
) -> int:
    """Embed every regis_moments row that has no embeddings row yet.

    If `user_id` is provided, scope to that user; otherwise process all users.
    Returns the count of rows successfully embedded.
    """
    sql = [
        "SELECT rm.id::text, rm.user_id::text, rm.content",
        "FROM regis_moments rm",
        "LEFT JOIN embeddings e",
        "  ON e.source_type = %s AND e.source_id = rm.id",
        "WHERE e.id IS NULL",
        "  AND rm.content IS NOT NULL",
        "  AND length(trim(rm.content)) > 0",
    ]
    params: list = [REGIS_MOMENT_SOURCE_TYPE]
    if user_id:
        sql.append("AND rm.user_id = %s")
        params.append(user_id)
    sql.append("ORDER BY rm.created_at ASC")
    sql.append("LIMIT %s")
    params.append(limit)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("\n".join(sql), tuple(params))
        rows = cur.fetchall()

    n_ok = 0
    for moment_id, uid, content in rows:
        result = embed_regis_moment(uid, moment_id, content)
        if result is not None:
            n_ok += 1
    return n_ok


def _main() -> int:
    ap = argparse.ArgumentParser(
        description="Backfill embeddings for regis_moments rows that lack one."
    )
    ap.add_argument(
        "--backfill",
        action="store_true",
        help="Run the backfill (otherwise just print a count of missing rows).",
    )
    ap.add_argument("--user-id", default=None, help="Scope to one user (default: all users).")
    ap.add_argument("--limit", type=int, default=1000)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.backfill:
        n = backfill_regis_moment_embeddings(user_id=args.user_id, limit=args.limit)
        print(f"Backfilled {n} regis_moment embedding(s).")
        return 0

    # Just report the gap.
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM regis_moments rm
            LEFT JOIN embeddings e
              ON e.source_type = %s AND e.source_id = rm.id
            WHERE e.id IS NULL
              AND rm.content IS NOT NULL
              AND length(trim(rm.content)) > 0
            """,
            (REGIS_MOMENT_SOURCE_TYPE,),
        )
        missing = cur.fetchone()[0]
    print(f"{missing} regis_moments row(s) missing an embedding.")
    print("Run with --backfill to embed them.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
