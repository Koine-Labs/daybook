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
# SQL-efficiency cutoff for the history scan; NOT the shaping knob. The EWMA
# is shaped entirely by BASELINE_DRIFT_HALF_LIFE_DAYS=180 — rows older than
# ~3 half-lives (540d) contribute negligible weight (<12.5%), so we can drop
# them from the scan without changing the result meaningfully.
MAX_LOOKBACK_DAYS = 540
BASELINE_REASON = "nightly baseline snapshot"
BASELINE_SOURCE = "baseline"

# Shared SQL fragment for "current trait value" readers. Excludes both
# baseline snapshots and decay nudges so callers see the most recent REAL
# signal (chat heuristic or dream-drift). Decay/baseline rows are derived
# state, not signal — surfacing them as "the current trait value" defeats
# the two-time-scale design: a nightly baseline write at 0.50 would
# otherwise mask whatever the dial actually drifted to during the day.
#
# Any new SELECT against regis_trait_history that wants "where the dial is
# right now for rendering / context" MUST apply this filter. See
# fetch_current_trait_values() for the canonical reader.
CURRENT_VALUE_SOURCE_FILTER = (
    "(source IS NULL OR source NOT IN ('baseline', 'decay'))"
)


def fetch_current_trait_values(user_id: str) -> dict[str, float]:
    """Latest signal-sourced value per trait_name for this user.

    Excludes source IN ('baseline', 'decay') — those are derived rows, not
    signal. Returns {} if no signal history exists yet.

    This is the canonical reader. All non-decay-engine callers that need
    "the current value of each trait" should use this helper rather than
    rolling their own SELECT, otherwise a future source-filter change has
    to be replayed across N call sites.
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT ON (trait_name) trait_name, value
            FROM regis_trait_history
            WHERE user_id = %s
              AND {CURRENT_VALUE_SOURCE_FILTER}
            ORDER BY trait_name, changed_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    return {r[0]: float(r[1]) for r in rows}


def compute_baseline(
    user_id: str,
    trait_name: str,
    *,
    half_life_days: int = BASELINE_DRIFT_HALF_LIFE_DAYS,
    now: datetime | None = None,
) -> float | None:
    """Exponentially-weighted average of trait_name over the user's history.

    Recent history gets weight ~1, history half_life_days old gets weight 0.5.
    Excludes rows where source IN ('decay', 'baseline') so the baseline is
    grounded in real signal only — otherwise it would drift toward whatever
    the decay engine wrote last night, creating a feedback loop.

    The scan window is hard-capped at MAX_LOOKBACK_DAYS (~3 half-lives) for
    SQL efficiency; older rows would weigh <12.5% and don't move the average
    meaningfully.

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
                now - _days(MAX_LOOKBACK_DAYS),
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
