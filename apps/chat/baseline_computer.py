"""Learned baselines for Regis's drifting personality dials.

For each trait, computes a slow-moving "baseline self" from the user's
trait_history via an exponentially-weighted moving average (EWMA). Recent
rows weigh ~1; rows BASELINE_DRIFT_HALF_LIFE_DAYS old weigh 0.5; etc.

This baseline is the target that trait_decay (the fast layer) pulls toward
each night. Persisting it as a row in regis_trait_history (with
source='baseline') lets downstream readers grab it without recomputing.

Companion to trait_decay.py.
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from datetime import datetime, timezone

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402


logger = logging.getLogger(__name__)


BASELINE_DRIFT_HALF_LIFE_DAYS = 180
BASELINE_WINDOW_DAYS = 90  # how far back to look at all (older rows have ~0 weight anyway)
BASELINE_REASON = "nightly baseline snapshot"
BASELINE_SOURCE = "baseline"


def compute_baseline(
    user_id: str,
    trait_name: str,
    *,
    half_life_days: int = BASELINE_DRIFT_HALF_LIFE_DAYS,
    window_days: int = BASELINE_WINDOW_DAYS,
    now: datetime | None = None,
) -> float | None:
    """Exponentially-weighted average of trait_name over the user's history.

    Recent history gets weight ~1, history half_life_days old gets weight 0.5.
    Excludes rows where source IN ('decay', 'baseline') so the baseline is
    grounded in real signal only — otherwise it would drift toward whatever
    the decay engine wrote last night, creating a feedback loop.

    Returns None if no history exists for this trait."""
    now = now or datetime.now(timezone.utc)
    # ln(2) / half_life — exponential decay rate in "per day"
    lam = math.log(2.0) / float(half_life_days)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT value, changed_at
            FROM regis_trait_history
            WHERE user_id = %s
              AND trait_name = %s
              AND (source IS NULL OR source NOT IN ('decay', 'baseline'))
              AND changed_at >= %s
            ORDER BY changed_at ASC
            """,
            (
                user_id,
                trait_name,
                now - _days(window_days * 6),  # generous lookback; weights die off fast
            ),
        )
        rows = cur.fetchall()

    if not rows:
        return None

    num = 0.0
    den = 0.0
    for value, changed_at in rows:
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - changed_at).total_seconds() / 86400.0)
        w = math.exp(-lam * age_days)
        num += w * float(value)
        den += w

    if den <= 0.0:
        return None
    return num / den


def compute_all_baselines(
    user_id: str,
    *,
    half_life_days: int = BASELINE_DRIFT_HALF_LIFE_DAYS,
    window_days: int = BASELINE_WINDOW_DAYS,
    now: datetime | None = None,
) -> dict[str, float]:
    """Compute EWMA baseline for every distinct trait_name in the user's history.

    Excludes rows where source IN ('decay', 'baseline') when enumerating traits
    too — a trait that ONLY has decay rows shouldn't have a baseline (yet).
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT trait_name
            FROM regis_trait_history
            WHERE user_id = %s
              AND (source IS NULL OR source NOT IN ('decay', 'baseline'))
            ORDER BY trait_name
            """,
            (user_id,),
        )
        trait_names = [r[0] for r in cur.fetchall()]

    out: dict[str, float] = {}
    for t in trait_names:
        b = compute_baseline(
            user_id,
            t,
            half_life_days=half_life_days,
            window_days=window_days,
            now=now,
        )
        if b is not None:
            out[t] = b
    return out


def persist_baseline(
    user_id: str,
    trait_name: str,
    value: float,
    *,
    reason: str = BASELINE_REASON,
    when: datetime | None = None,
) -> None:
    """Write a single regis_trait_history row tagged source='baseline'.

    Stores the latest baseline so downstream readers (trait_decay) can grab it
    without recomputing the EWMA every night. `delta` is left NULL — baselines
    aren't deltas, they're snapshots.
    """
    value = float(max(0.0, min(1.0, value)))
    with get_conn() as conn, conn.cursor() as cur:
        if when is None:
            cur.execute(
                """
                INSERT INTO regis_trait_history
                  (user_id, trait_name, value, delta, reason, source)
                VALUES (%s, %s, %s, NULL, %s, %s)
                """,
                (user_id, trait_name, value, reason, BASELINE_SOURCE),
            )
        else:
            cur.execute(
                """
                INSERT INTO regis_trait_history
                  (user_id, trait_name, value, delta, reason, source, changed_at)
                VALUES (%s, %s, %s, NULL, %s, %s, %s)
                """,
                (user_id, trait_name, value, reason, BASELINE_SOURCE, when),
            )
        conn.commit()


def get_latest_baseline(user_id: str, trait_name: str) -> float | None:
    """Fetch the most recent persisted baseline for a trait, if any."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT value FROM regis_trait_history
            WHERE user_id = %s AND trait_name = %s AND source = %s
            ORDER BY changed_at DESC LIMIT 1
            """,
            (user_id, trait_name, BASELINE_SOURCE),
        )
        row = cur.fetchone()
    return float(row[0]) if row else None


def _days(n: int):
    from datetime import timedelta

    return timedelta(days=n)


def _main() -> int:
    ap = argparse.ArgumentParser(description="Compute and optionally persist EWMA trait baselines.")
    ap.add_argument("--user-id", default=_paths.DEFAULT_USER_ID)
    ap.add_argument("--persist", action="store_true", help="write source='baseline' rows")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    baselines = compute_all_baselines(user_id=args.user_id)
    if not baselines:
        print("(no history)")
        return 0
    for t, v in sorted(baselines.items()):
        print(f"  {t:>14s}  {v:.4f}")
    if args.persist:
        for t, v in baselines.items():
            persist_baseline(args.user_id, t, v)
        print(f"persisted {len(baselines)} baseline row(s)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
