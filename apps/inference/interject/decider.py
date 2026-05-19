"""Composite auto-interjection decider.

v0 = simple weighted sum of inputs against a conservative threshold.
Future: learned (bandit / RL) decider trained on interject_decisions outcomes.

Starting weights (will be tuned):
    score = 0.30 * user_receptivity
          + 0.30 * novelty
          + 0.20 * min(silence_minutes / 30, 1.0)
          + 0.20 * time_of_day_score
    threshold = 0.65   # high — prefer NOT to interject
"""
from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# apps/inference/ on sys.path for `from db import get_conn`
INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

from db import get_conn  # noqa: E402

# v0 weights — document these as starting values; future learning will tune.
W_RECEPTIVITY = 0.30
W_NOVELTY = 0.30
W_SILENCE = 0.20
W_TIME_OF_DAY = 0.20
DEFAULT_THRESHOLD = 0.65
SILENCE_SATURATION_SECONDS = 30 * 60  # 30 min of silence saturates the silence input

_routing_guard = threading.local()


@dataclass
class InterjectContext:
    user_id: str
    trigger_kind: str
    recent_silence_seconds: float
    user_receptivity: float
    novelty: float
    time_of_day_score: float
    active_traits: dict = field(default_factory=dict)
    trigger_payload: dict = field(default_factory=dict)


@dataclass
class InterjectDecision:
    decided: bool
    score: float
    threshold: float
    reason: str
    persisted_id: str | None = None


def decide(
    ctx: InterjectContext,
    *,
    persist: bool = True,
    threshold: float = DEFAULT_THRESHOLD,
) -> InterjectDecision:
    """Run the composite decider. Returns an InterjectDecision (always)."""
    if os.environ.get("DAYBOOK_LEARNED_DECIDER") and not getattr(
        _routing_guard, "active", False,
    ):
        _routing_guard.active = True
        try:
            from .learned_decider import learned_decide

            return learned_decide(ctx, persist=persist)
        except Exception as e:
            print(f"[decider] learned_decide failed, using fixed weights: {e}")
        finally:
            _routing_guard.active = False

    receptivity = _clamp01(ctx.user_receptivity)
    novelty = _clamp01(ctx.novelty)
    silence_term = _clamp01(ctx.recent_silence_seconds / SILENCE_SATURATION_SECONDS)
    time_term = _clamp01(ctx.time_of_day_score)

    score = (
        W_RECEPTIVITY * receptivity
        + W_NOVELTY * novelty
        + W_SILENCE * silence_term
        + W_TIME_OF_DAY * time_term
    )
    decided = score >= threshold

    reason = _build_reason(
        decided=decided,
        score=score,
        threshold=threshold,
        receptivity=receptivity,
        novelty=novelty,
        silence_term=silence_term,
        time_term=time_term,
    )

    decision = InterjectDecision(
        decided=decided,
        score=round(score, 4),
        threshold=threshold,
        reason=reason,
    )

    if persist:
        decision.persisted_id = _persist_decision(ctx, decision)

    return decision


def _build_reason(
    *,
    decided: bool,
    score: float,
    threshold: float,
    receptivity: float,
    novelty: float,
    silence_term: float,
    time_term: float,
) -> str:
    verdict = "spoke" if decided else "held silence"
    return (
        f"{verdict}: score={score:.3f} thr={threshold:.3f} "
        f"(recept={receptivity:.2f} novelty={novelty:.2f} "
        f"silence={silence_term:.2f} tod={time_term:.2f})"
    )


def _persist_decision(
    ctx: InterjectContext,
    decision: InterjectDecision,
) -> str | None:
    """Write to interject_decisions. Returns new id, or None on failure."""
    snapshot = {
        "user_receptivity": ctx.user_receptivity,
        "novelty": ctx.novelty,
        "recent_silence_seconds": ctx.recent_silence_seconds,
        "time_of_day_score": ctx.time_of_day_score,
        "active_traits": ctx.active_traits,
        "trigger_payload": ctx.trigger_payload,
        "score": decision.score,
        "threshold": decision.threshold,
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
    except Exception as e:  # pragma: no cover - persistence is best-effort
        print(f"[decider] persist failed: {e}")
        return None


def attach_resulting_moment(
    decision_id: str,
    moment_id: str,
) -> None:
    """Link a regis_moments row to a previously-persisted decision."""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE interject_decisions SET resulting_moment_id=%s WHERE id=%s",
                (moment_id, decision_id),
            )
            conn.commit()
    except Exception as e:  # pragma: no cover
        print(f"[decider] attach_resulting_moment failed: {e}")


def _clamp01(x: float) -> float:
    if x is None:
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)
