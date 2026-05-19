"""Stage B — Thompson-sampling contextual bandit over interject features.

Drop-in replacement for `decider.decide()`.

Behavior:
  - Pull all interject_decisions for the user with non-NULL user_outcome.
  - If fewer than MIN_LABELED (50): fall back to fixed-weight decider with
    a `fallback_to_fixed (n_labels=N): ...` reason prefix.
  - Otherwise: maintain per-feature-bucket Beta(alpha, beta) posteriors over
    the discretized features. For the current ctx, look up the bucket each
    feature lands in, sample p ~ Beta from each, combine via geometric mean,
    threshold at 0.5.

Reward mapping:
  positive -> success (alpha += 1)
  negative -> failure (beta  += 1)
  neutral  -> half-failure (beta += 0.5)
  ignored  -> half-failure (beta += 0.5)

Persists into interject_decisions with a context snapshot describing the
sampled probabilities per feature and the combined score. Never raises —
any error falls back to the fixed-weight decider.
"""
from __future__ import annotations

import json
import logging
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402

from . import decider as fixed_decider  # noqa: E402
from .decider import InterjectContext, InterjectDecision  # noqa: E402

logger = logging.getLogger(__name__)

MIN_LABELED = 50
LEARNED_THRESHOLD = 0.5
BETA_PRIOR_ALPHA = 1.0
BETA_PRIOR_BETA = 1.0

REWARD_DELTAS: dict[str, tuple[float, float]] = {
    "positive": (1.0, 0.0),
    "negative": (0.0, 1.0),
    "neutral": (0.0, 0.5),
    "ignored": (0.0, 0.5),
}


def learned_decide(
    ctx: InterjectContext, *, persist: bool = True,
) -> InterjectDecision:
    """Thompson-sampling decider. Falls back to fixed weights on any error."""
    try:
        labels = _fetch_labeled(ctx.user_id)
    except Exception as e:
        logger.warning("[learned_decider] label fetch failed: %s", e)
        return _fallback(ctx, persist=persist, prefix=f"fallback_to_fixed (label_fetch_error: {e})")

    if len(labels) < MIN_LABELED:
        return _fallback(
            ctx, persist=persist,
            prefix=f"fallback_to_fixed (n_labels={len(labels)})",
        )

    try:
        posteriors = _build_posteriors(labels)
        feature_buckets = _bucketize_ctx(ctx)
        sampled: dict[str, float] = {}
        for feature, bucket in feature_buckets.items():
            alpha, beta = posteriors.get(feature, {}).get(
                bucket, (BETA_PRIOR_ALPHA, BETA_PRIOR_BETA),
            )
            sampled[feature] = _beta_sample(alpha, beta)

        score = _geometric_mean(sampled.values())
        decided = score >= LEARNED_THRESHOLD
        reason = _build_reason(
            decided=decided, score=score, n_labels=len(labels),
            sampled=sampled, buckets=feature_buckets,
        )
        decision = InterjectDecision(
            decided=decided,
            score=round(score, 4),
            threshold=LEARNED_THRESHOLD,
            reason=reason,
        )
        if persist:
            decision.persisted_id = _persist_learned(
                ctx=ctx, decision=decision,
                sampled=sampled, buckets=feature_buckets,
                n_labels=len(labels),
            )
        return decision
    except Exception as e:
        logger.warning("[learned_decider] sampling failed, falling back: %s", e)
        return _fallback(ctx, persist=persist, prefix=f"fallback_to_fixed (sampling_error: {e})")


def _fallback(
    ctx: InterjectContext, *, persist: bool, prefix: str,
) -> InterjectDecision:
    decision = fixed_decider.decide(ctx, persist=persist)
    decision.reason = f"{prefix}: {decision.reason}"
    return decision


def _fetch_labeled(user_id: str) -> list[tuple[dict, str]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT context_snapshot, user_outcome
            FROM interject_decisions
            WHERE user_id = %s
              AND user_outcome IS NOT NULL
            """,
            (user_id,),
        )
        out: list[tuple[dict, str]] = []
        for snapshot, outcome in cur.fetchall():
            if isinstance(snapshot, str):
                try:
                    snapshot = json.loads(snapshot)
                except Exception:
                    snapshot = {}
            out.append((snapshot or {}, outcome))
        return out


def _build_posteriors(
    labels: list[tuple[dict, str]],
) -> dict[str, dict[str, tuple[float, float]]]:
    posteriors: dict[str, dict[str, tuple[float, float]]] = {}
    for snapshot, outcome in labels:
        d_alpha, d_beta = REWARD_DELTAS.get(outcome, (0.0, 0.0))
        if d_alpha == 0.0 and d_beta == 0.0:
            continue
        for feature, bucket in _bucketize_snapshot(snapshot).items():
            feat_map = posteriors.setdefault(feature, {})
            a, b = feat_map.get(bucket, (BETA_PRIOR_ALPHA, BETA_PRIOR_BETA))
            feat_map[bucket] = (a + d_alpha, b + d_beta)
    return posteriors


def _bucketize_ctx(ctx: InterjectContext) -> dict[str, str]:
    return {
        "receptivity": _bucket_unit(ctx.user_receptivity),
        "novelty": _bucket_unit(ctx.novelty),
        "silence": _bucket_silence(ctx.recent_silence_seconds),
        "time_of_day": _bucket_time_of_day(ctx.time_of_day_score),
    }


def _bucketize_snapshot(snapshot: dict) -> dict[str, str]:
    return {
        "receptivity": _bucket_unit(snapshot.get("user_receptivity")),
        "novelty": _bucket_unit(snapshot.get("novelty")),
        "silence": _bucket_silence(snapshot.get("recent_silence_seconds")),
        "time_of_day": _bucket_time_of_day(snapshot.get("time_of_day_score")),
    }


def _bucket_unit(x: float | None) -> str:
    if x is None:
        return "unk"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "unk"
    if v < 0.0:
        v = 0.0
    if v >= 1.0:
        return "0.8-1.0"
    edges = (0.2, 0.4, 0.6, 0.8, 1.0)
    lowers = (0.0, 0.2, 0.4, 0.6, 0.8)
    for lo, hi in zip(lowers, edges):
        if v < hi:
            return f"{lo:.1f}-{hi:.1f}"
    return "0.8-1.0"


def _bucket_silence(seconds: float | None) -> str:
    if seconds is None:
        return "unk"
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return "unk"
    if s < 5 * 60:
        return "0-5m"
    if s < 15 * 60:
        return "5-15m"
    if s < 30 * 60:
        return "15-30m"
    return "30m+"


def _bucket_time_of_day(score: float | None) -> str:
    if score is None:
        return "unk"
    try:
        v = float(score)
    except (TypeError, ValueError):
        return "unk"
    if v >= 0.75:
        return "day"
    if v >= 0.3:
        return "morning_evening"
    return "night"


def _beta_sample(alpha: float, beta: float) -> float:
    a = max(float(alpha), 1e-3)
    b = max(float(beta), 1e-3)
    return random.betavariate(a, b)


def _geometric_mean(values) -> float:
    values = [max(float(v), 1e-9) for v in values]
    if not values:
        return 0.0
    return math.exp(sum(math.log(v) for v in values) / len(values))


def _build_reason(
    *, decided: bool, score: float, n_labels: int,
    sampled: dict[str, float], buckets: dict[str, str],
) -> str:
    verdict = "spoke" if decided else "held silence"
    sample_str = " ".join(
        f"{k}[{buckets[k]}]={sampled[k]:.2f}" for k in sorted(sampled)
    )
    return (
        f"learned/{verdict}: score={score:.3f} thr={LEARNED_THRESHOLD:.2f} "
        f"n={n_labels} {sample_str}"
    )


def _persist_learned(
    *, ctx: InterjectContext, decision: InterjectDecision,
    sampled: dict[str, float], buckets: dict[str, str], n_labels: int,
) -> str | None:
    snapshot = {
        "user_receptivity": ctx.user_receptivity,
        "novelty": ctx.novelty,
        "recent_silence_seconds": ctx.recent_silence_seconds,
        "time_of_day_score": ctx.time_of_day_score,
        "active_traits": ctx.active_traits,
        "trigger_payload": ctx.trigger_payload,
        "score": decision.score,
        "threshold": decision.threshold,
        "decider": "learned",
        "n_labels": n_labels,
        "sampled": sampled,
        "buckets": buckets,
    }
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO interject_decisions
                    (user_id, decided_at, trigger_kind, context_snapshot,
                     decision, reason)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                RETURNING id
                """,
                (
                    ctx.user_id,
                    datetime.now(timezone.utc),
                    ctx.trigger_kind,
                    json.dumps(snapshot, default=str),
                    decision.decided,
                    decision.reason,
                ),
            )
            new_id = str(cur.fetchone()[0])
            conn.commit()
        return new_id
    except Exception as e:
        logger.warning("[learned_decider] persist failed: %s", e)
        return None


__all__ = ["learned_decide", "MIN_LABELED"]
