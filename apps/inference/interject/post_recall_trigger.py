"""First concrete auto-interjection trigger: post-recall reflection.

Called by recall.capture after a successful dream capture. The decider runs;
if decision=True, the wisp composer (or full voice_chain) produces a brief
reflection that arrives ~moments later as a follow-up to the "Held." ack.

Triggers must NEVER raise — failures log and return a held-silence decision.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))

APPS_DIR = INFERENCE_DIR.parent
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from db import get_conn  # noqa: E402

from .decider import (  # noqa: E402
    InterjectContext,
    InterjectDecision,
    attach_resulting_moment,
    decide,
)
from .triggers import register  # noqa: E402


@register("post_recall")
def post_recall_trigger(
    *,
    user_id: str,
    dream_recall_id: str,
    dream_text: str,
) -> InterjectDecision:
    """Fire the post-recall reflection trigger.

    Decider runs; if decision=True, composer produces a brief reflection and
    (optionally) the full voice chain speaks it. Returns the decision either
    way. Never raises.
    """
    try:
        silence_seconds = _recent_silence_seconds(user_id)
        time_of_day_score = _time_of_day_score()
        active_traits = _active_traits(user_id)

        ctx = InterjectContext(
            user_id=user_id,
            trigger_kind="post_recall",
            recent_silence_seconds=silence_seconds,
            user_receptivity=0.7,  # default high — user just engaged
            novelty=0.9,            # dream content is novel by definition
            time_of_day_score=time_of_day_score,
            active_traits=active_traits,
            trigger_payload={
                "dream_recall_id": dream_recall_id,
                "dream_text": dream_text[:500],
            },
        )

        decision = decide(ctx)

        if decision.decided:
            moment_id = _compose_and_maybe_speak(user_id=user_id, dream_text=dream_text)
            if moment_id and decision.persisted_id:
                attach_resulting_moment(decision.persisted_id, moment_id)

        return decision
    except Exception as e:
        print(f"[post_recall_trigger] error (held silence): {e}")
        return InterjectDecision(
            decided=False,
            score=0.0,
            threshold=0.65,
            reason=f"error: {e}",
        )


def _compose_and_maybe_speak(*, user_id: str, dream_text: str) -> str | None:
    """Compose a post-recall reflection; speak it if voice_chain is available.

    Returns the regis_moments.id of the resulting moment, or None on failure.
    """
    explicit_context = (
        f"User just logged a dream recall. The contents: {dream_text[:500]}\n"
        "Reflect briefly — one or two sentences. Do not interpret or analyze. "
        "Speak as if continuing a thought, not delivering a verdict."
    )

    try:
        from wisp.voice_chain import speak_moment  # type: ignore
        try:
            result = speak_moment(
                user_id=user_id,
                moment_kind="post_recall_reflection",
                explicit_context=explicit_context,
                retrieval_query=dream_text,
                retrieval_source_types=("dream_recall",),
                persist=True,
                dry_run=True,
            )
            return result.get("regis_moment_id")
        except Exception as e:
            print(f"[post_recall_trigger] voice_chain failed, falling back: {e}")
    except ImportError:
        pass

    # Fallback: text-only composer (no synthesis).
    try:
        from wisp.composer import compose_utterance  # type: ignore

        composed = compose_utterance(
            user_id=user_id,
            moment_kind="post_recall_reflection",
            explicit_context=explicit_context,
            retrieval_query=dream_text,
            retrieval_source_types=("dream_recall",),
            persist=True,
        )
        return composed.persisted_moment_id
    except Exception as e:
        print(f"[post_recall_trigger] composer failed: {e}")
        return None


def _recent_silence_seconds(user_id: str) -> float:
    """Seconds since the most recent regis_moments row for this user."""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT occurred_at FROM regis_moments "
                "WHERE user_id=%s ORDER BY occurred_at DESC LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
        if row is None or row[0] is None:
            return float(SILENCE_FALLBACK_SECONDS)
        delta = datetime.now(timezone.utc) - row[0]
        return max(0.0, delta.total_seconds())
    except Exception:
        return float(SILENCE_FALLBACK_SECONDS)


def _time_of_day_score() -> float:
    """Morning = high (dream recall is a morning ritual); else moderate."""
    hour = datetime.now(timezone.utc).astimezone().hour
    if 5 <= hour <= 11:
        return 0.8
    return 0.5


def _active_traits(user_id: str) -> dict:
    """Latest value per trait_name for this user."""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (trait_name) trait_name, value
                FROM regis_trait_history
                WHERE user_id = %s
                ORDER BY trait_name, changed_at DESC
                """,
                (user_id,),
            )
            return {name: float(val) for name, val in cur.fetchall()}
    except Exception:
        return {}


SILENCE_FALLBACK_SECONDS = 30 * 60  # 30 min — assume a healthy gap if unknown
