"""Cluster dormancy lifecycle for I-Model clusters.

Clusters fire when the activator surfaces them against new evidence. If a
cluster hasn't fired in DORMANCY_THRESHOLD_DAYS, we mark it dormant — it
stops shaping current prompts but is preserved (recoverable when matching
evidence returns).

Reactivation is automatic via two paths, both calling ``reactivate_if_matched``:
  - The activator (``get_active_clusters``) scans dormant clusters' centroids
    too; any dormant match above ``min_similarity`` is flipped to 'active'
    (so it can shape prompts on the next call).
  - The clusterer's supersession detector also stamps the child cluster
    active when recording a 'supersedes' lineage row.

CLI:
    python -m imodels.cluster_dormancy --user-id <uuid> [--dry-run]
                                       [--threshold-days N]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402

logger = logging.getLogger(__name__)

# Module-level knob: a cluster goes dormant after this many days without firing.
DORMANCY_THRESHOLD_DAYS = 60

# Reactivation window — dormant clusters whose last_activated_at was bumped
# within this many hours (because the activator or clusterer touched them)
# get flipped back to 'active' in the same sweep.
REACTIVATION_WINDOW_HOURS = 24


def sweep_dormancy(
    user_id: str,
    *,
    threshold_days: int = DORMANCY_THRESHOLD_DAYS,
    persist: bool = True,
) -> dict:
    """Mark stale clusters dormant and revive freshly-fired dormant ones.

    Two passes per call, both scoped to ``user_id``:

      1. Any cluster with ``status='active'`` whose ``last_activated_at`` is
         older than ``now() - threshold_days`` is flipped to ``'dormant'``.
         (Clusters with NULL last_activated_at are treated as fresh — the
         backfill in 0006 ensures none exist on day one.)
      2. Any cluster with ``status='dormant'`` whose ``last_activated_at`` is
         within the last REACTIVATION_WINDOW_HOURS is flipped to ``'active'``.
         This handles the case where evidence re-matched a dormant cluster
         (the activator / clusterer bumped the timestamp without changing
         status).

    Returns {marked_dormant: N, reactivated: M}.
    """
    if not persist:
        return _dry_run_counts(user_id=user_id, threshold_days=threshold_days)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE i_model_clusters
               SET status = 'dormant'
             WHERE user_id = %s
               AND status = 'active'
               AND last_activated_at IS NOT NULL
               AND last_activated_at < now() - (%s || ' days')::interval
            """,
            (user_id, str(threshold_days)),
        )
        marked_dormant = cur.rowcount or 0

        cur.execute(
            """
            UPDATE i_model_clusters
               SET status = 'active'
             WHERE user_id = %s
               AND status = 'dormant'
               AND last_activated_at IS NOT NULL
               AND last_activated_at > now() - (%s || ' hours')::interval
            """,
            (user_id, str(REACTIVATION_WINDOW_HOURS)),
        )
        reactivated = cur.rowcount or 0
        conn.commit()

    logger.info(
        "cluster_dormancy sweep user=%s threshold_days=%d marked_dormant=%d reactivated=%d",
        user_id,
        threshold_days,
        marked_dormant,
        reactivated,
    )
    return {"marked_dormant": marked_dormant, "reactivated": reactivated}


def reactivate_if_matched(user_id: str, cluster_id: str) -> bool:
    """Flip a (possibly-dormant) cluster back to active and stamp the timestamp.

    Idempotent — calling on an already-active cluster simply re-stamps
    ``last_activated_at``. Returns True if the row was found and updated.
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE i_model_clusters
               SET status = 'active',
                   last_activated_at = now()
             WHERE user_id = %s
               AND id = %s
            """,
            (user_id, cluster_id),
        )
        touched = (cur.rowcount or 0) > 0
        conn.commit()
    if touched:
        logger.info(
            "cluster_dormancy: reactivated cluster=%s user=%s",
            cluster_id,
            user_id,
        )
    return touched


def _dry_run_counts(*, user_id: str, threshold_days: int) -> dict:
    """Count what would change without writing — for --dry-run."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM i_model_clusters
             WHERE user_id = %s
               AND status = 'active'
               AND last_activated_at IS NOT NULL
               AND last_activated_at < now() - (%s || ' days')::interval
            """,
            (user_id, str(threshold_days)),
        )
        would_dormant = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT count(*) FROM i_model_clusters
             WHERE user_id = %s
               AND status = 'dormant'
               AND last_activated_at IS NOT NULL
               AND last_activated_at > now() - (%s || ' hours')::interval
            """,
            (user_id, str(REACTIVATION_WINDOW_HOURS)),
        )
        would_reactivate = int(cur.fetchone()[0])
    return {
        "marked_dormant": would_dormant,
        "reactivated": would_reactivate,
        "dry_run": True,
    }


def _main() -> int:
    ap = argparse.ArgumentParser(prog="cluster_dormancy")
    ap.add_argument("--user-id", required=True)
    ap.add_argument(
        "--threshold-days",
        type=int,
        default=DORMANCY_THRESHOLD_DAYS,
        help=f"days without activation before dormancy (default {DORMANCY_THRESHOLD_DAYS})",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    result = sweep_dormancy(
        args.user_id,
        threshold_days=args.threshold_days,
        persist=not args.dry_run,
    )
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(_main())


__all__ = [
    "DORMANCY_THRESHOLD_DAYS",
    "REACTIVATION_WINDOW_HOURS",
    "reactivate_if_matched",
    "sweep_dormancy",
]
