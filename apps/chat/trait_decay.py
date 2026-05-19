"""Nightly trait decay — pulls each trait gently toward its learned baseline.

Two time scales coexist in regis_trait_history:

  FAST (days)  — per-turn drift from trait_drift.py (heuristic) and
                 trait_drift_from_dreams.py (LLM-driven). Capped at 4*MAX_DELTA
                 per UTC day per trait so a single intense day can't spike a
                 dial runaway.

  SLOW (months) — baseline_computer.compute_baseline writes source='baseline'
                  rows nightly using an EWMA of the trait's history. This module
                  then nudges the latest value toward that baseline.

  delta = (baseline - current) * (1 - 0.5**(1/HALF_LIFE_DAYS))

The thesis: Regis should remember you across years. Without decay, every
trait dial drifted by an unusual conversation stays there forever and the
character ratchets in whatever direction the latest event pushed. With
decay, non-rehearsed signals fade and only persistent patterns shape the
baseline.

Half-life of 90 days means: after 90 days of no reinforcing signal, the
gap between current value and baseline halves.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from . import _paths  # noqa: F401
from .baseline_computer import (
    compute_baseline,
    get_latest_baseline,
    persist_baseline,
)
from db import get_conn  # noqa: E402


logger = logging.getLogger(__name__)


TRAIT_DECAY_HALF_LIFE_DAYS = 90
# per-day decay rate: distance-to-baseline shrinks by this fraction each night.
# 1 - 0.5**(1/90) ≈ 0.007675
_DECAY_RATE = 1.0 - 0.5 ** (1.0 / TRAIT_DECAY_HALF_LIFE_DAYS)

MIN_DELTA_MAGNITUDE = 0.001  # below this, skip the write — noise
DECAY_SOURCE = "decay"


@dataclass
class DecayDelta:
    trait: str
    current: float
    baseline: float
    delta: float
    new_value: float
    reason: str


def apply_nightly_decay(
    user_id: str,
    *,
    persist: bool = True,
    dry_run: bool = False,
    half_life_days: int = TRAIT_DECAY_HALF_LIFE_DAYS,
    now: datetime | None = None,
    recompute_baseline: bool = True,
    **_unused: Any,  # for scheduler compatibility
) -> list[DecayDelta]:
    """Pull every trait gently toward its baseline.

    For each trait with at least one signal row:
      1. Get latest current value (the most recent row regardless of source)
      2. Get latest baseline (source='baseline'); recompute on the fly if missing
      3. delta = (baseline - current) * decay_rate
      4. If |delta| < MIN_DELTA_MAGNITUDE → skip (noise)
      5. Insert a row with source='decay'

    `dry_run=True` returns the proposed deltas without persisting.
    `persist=False` is an alias for `dry_run=True` (and the scheduler-friendly form).
    """
    if dry_run:
        persist = False

    now = now or datetime.now(timezone.utc)
    rate = 1.0 - 0.5 ** (1.0 / float(half_life_days))

    currents = _fetch_latest_values(user_id=user_id)
    if not currents:
        logger.info("apply_nightly_decay: no trait history for user — nothing to decay")
        return []

    out: list[DecayDelta] = []
    for trait_name, current in currents.items():
        baseline = get_latest_baseline(user_id, trait_name)
        if baseline is None and recompute_baseline:
            baseline = compute_baseline(user_id, trait_name, now=now)
            if baseline is not None and persist:
                persist_baseline(user_id, trait_name, baseline, when=now)

        if baseline is None:
            logger.debug("apply_nightly_decay: no baseline for %s; skipping", trait_name)
            continue

        gap = baseline - current
        delta = gap * rate
        if abs(delta) < MIN_DELTA_MAGNITUDE:
            continue

        new_value = max(0.0, min(1.0, current + delta))
        reason = f"decay toward baseline ({baseline:.2f}, half-life {half_life_days}d)"
        rec = DecayDelta(
            trait=trait_name,
            current=current,
            baseline=baseline,
            delta=delta,
            new_value=new_value,
            reason=reason,
        )
        if persist:
            _persist_decay(
                user_id=user_id,
                trait=trait_name,
                new_value=new_value,
                delta=delta,
                reason=reason,
                when=now,
            )
        out.append(rec)

    logger.info(
        "apply_nightly_decay: %s %d delta(s) for user %s",
        "persisted" if persist else "computed",
        len(out),
        user_id,
    )
    return out


def simulate_days(
    user_id: str,
    n_days: int,
    *,
    persist: bool = False,
    half_life_days: int = TRAIT_DECAY_HALF_LIFE_DAYS,
) -> dict[str, Any]:
    """Run apply_nightly_decay N times, advancing 1 day per iteration.

    Returns:
      {
        "final": {trait: value},
        "trajectory": {trait: [v0, v1, ..., vN]},
      }

    persist=False (default) keeps this side-effect-free — we don't want to
    write 90 fake decay rows to prod when sanity-checking the math.
    """
    now = datetime.now(timezone.utc)
    # snapshot starting values from DB
    currents = dict(_fetch_latest_values(user_id=user_id))
    baselines: dict[str, float] = {}
    for t in currents:
        b = get_latest_baseline(user_id, t) or compute_baseline(user_id, t, now=now)
        if b is not None:
            baselines[t] = b

    rate = 1.0 - 0.5 ** (1.0 / float(half_life_days))
    trajectory: dict[str, list[float]] = {t: [v] for t, v in currents.items()}

    for _ in range(n_days):
        for t, v in list(currents.items()):
            b = baselines.get(t)
            if b is None:
                continue
            new_v = max(0.0, min(1.0, v + (b - v) * rate))
            currents[t] = new_v
            trajectory[t].append(new_v)

    if persist:
        # advance baseline timestamps day-by-day and write decay rows
        for i in range(n_days):
            when = now + timedelta(days=i + 1)
            apply_nightly_decay(user_id, persist=True, now=when, half_life_days=half_life_days)

    return {
        "final": dict(currents),
        "trajectory": trajectory,
        "baselines": baselines,
    }


# ---------------------------------------------------------------------------


def _fetch_latest_values(*, user_id: str) -> dict[str, float]:
    """Latest value per trait_name, regardless of source.

    The 'current' value is whatever was written most recently — could be from
    a chat heuristic, a dream reflection, a prior decay nudge, or a baseline
    snapshot. All four are legitimate "where the dial is right now".
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (trait_name) trait_name, value
            FROM regis_trait_history
            WHERE user_id = %s
              AND (source IS NULL OR source <> 'baseline')
            ORDER BY trait_name, changed_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    return {t: float(v) for t, v in rows}


def _persist_decay(
    *,
    user_id: str,
    trait: str,
    new_value: float,
    delta: float,
    reason: str,
    when: datetime | None = None,
) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        if when is None:
            cur.execute(
                """
                INSERT INTO regis_trait_history
                  (user_id, trait_name, value, delta, reason, source)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user_id, trait, new_value, delta, reason, DECAY_SOURCE),
            )
        else:
            cur.execute(
                """
                INSERT INTO regis_trait_history
                  (user_id, trait_name, value, delta, reason, source, changed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, trait, new_value, delta, reason, DECAY_SOURCE, when),
            )
        conn.commit()


def _main() -> int:
    ap = argparse.ArgumentParser(description="Apply nightly trait decay toward baselines.")
    ap.add_argument("--user-id", default=_paths.DEFAULT_USER_ID)
    ap.add_argument("--dry-run", action="store_true", help="don't write to DB; print proposed deltas")
    ap.add_argument("--simulate-days", type=int, default=0, help="run N day-steps and print trajectory")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.simulate_days > 0:
        result = simulate_days(args.user_id, args.simulate_days, persist=False)
        print(f"baselines: {result['baselines']}")
        print(f"final: {result['final']}")
        print("trajectory (first/last 3):")
        for t, traj in result["trajectory"].items():
            head = ", ".join(f"{v:.4f}" for v in traj[:3])
            tail = ", ".join(f"{v:.4f}" for v in traj[-3:])
            print(f"  {t:>14s}  [{head}, ..., {tail}]  (n={len(traj)})")
        return 0

    deltas = apply_nightly_decay(args.user_id, persist=not args.dry_run)
    print(f"{'(dry-run) ' if args.dry_run else ''}Applied {len(deltas)} decay delta(s):")
    for d in deltas:
        print(
            f"  {d.trait:>14s}  cur={d.current:.4f}  base={d.baseline:.4f}  "
            f"delta={d.delta:+.5f}  new={d.new_value:.4f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
