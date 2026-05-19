"""First concrete auto-interjection trigger: post-recall reflection.

Called by recall.capture after a successful dream capture. The decider runs;
if decision=True, the wisp composer (or full voice_chain) produces a brief
reflection that arrives ~moments later as a follow-up to the "Held." ack.

Triggers must NEVER raise — failures log and return a held-silence decision.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
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

logger = logging.getLogger(__name__)

# Fallback constants — used only when real derivation fails (DB down, no
# embedding, etc). These are the historical hardcoded values; keeping them as
# the last-resort default preserves prior behaviour on catastrophic failure.
FALLBACK_NOVELTY = 0.7
FALLBACK_RECEPTIVITY = 0.5  # conservative neutral when signal is thin
LEGACY_RECEPTIVITY = 0.7    # last-resort if DB itself is unreachable

# Receptivity window + min sample size for trusting the rolling rate.
RECEPTIVITY_LOOKBACK_HOURS = 24
RECEPTIVITY_MIN_SAMPLES = 3

# Novelty: how many prior recalls to average similarity against.
NOVELTY_TOP_K = 5


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
        novelty = _derive_novelty(
            user_id=user_id, dream_recall_id=dream_recall_id,
        )
        user_receptivity = _derive_receptivity(user_id=user_id)
        logger.info(
            "[post_recall_trigger] inputs user=%s recall=%s novelty=%.3f "
            "receptivity=%.3f silence_s=%.0f tod=%.2f",
            user_id, dream_recall_id, novelty, user_receptivity,
            silence_seconds, time_of_day_score,
        )

        ctx = InterjectContext(
            user_id=user_id,
            trigger_kind="post_recall",
            recent_silence_seconds=silence_seconds,
            user_receptivity=user_receptivity,
            novelty=novelty,
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
    """Latest signal-sourced value per trait. Excludes baseline/decay rows.

    Delegates to chat.baseline_computer.fetch_current_trait_values — see
    CURRENT_VALUE_SOURCE_FILTER for the rationale.
    """
    try:
        from chat.baseline_computer import fetch_current_trait_values  # type: ignore
        return fetch_current_trait_values(user_id)
    except Exception:
        return {}


SILENCE_FALLBACK_SECONDS = 30 * 60  # 30 min — assume a healthy gap if unknown


def _derive_novelty(*, user_id: str, dream_recall_id: str) -> float:
    """Novelty = 1 - mean(top-5 cosine similarities to prior dream_recalls).

    If this recall has no embedding yet (race with embedder), warn and return
    FALLBACK_NOVELTY. If the user has zero prior recalls, novelty=1.0 (all-new).
    DB failure => FALLBACK_NOVELTY with a warning.
    """
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT embedding::text FROM embeddings
                WHERE user_id=%s AND source_type='dream_recall'
                  AND source_id=%s
                ORDER BY created_at DESC LIMIT 1
                """,
                (user_id, dream_recall_id),
            )
            row = cur.fetchone()
        if row is None:
            logger.warning(
                "[post_recall_trigger] no embedding for recall %s — "
                "novelty fallback %.2f", dream_recall_id, FALLBACK_NOVELTY,
            )
            return FALLBACK_NOVELTY

        qvec = _parse_vector_literal(row[0])

        from embeddings.retrieve import retrieve_similar  # noqa: E402

        # Over-fetch by 1 so we can drop the self-hit (similarity == 1.0)
        hits = retrieve_similar(
            qvec,
            user_id=user_id,
            top_k=NOVELTY_TOP_K + 1,
            source_types=["dream_recall"],
        )
        prior = [
            h.similarity for h in hits if h.source_id != dream_recall_id
        ][:NOVELTY_TOP_K]
        if not prior:
            logger.info(
                "[post_recall_trigger] no prior recalls — novelty=1.0",
            )
            return 1.0
        mean_sim = sum(prior) / len(prior)
        novelty = max(0.0, min(1.0, 1.0 - mean_sim))
        logger.info(
            "[post_recall_trigger] novelty=%.3f from %d prior (mean_sim=%.3f)",
            novelty, len(prior), mean_sim,
        )
        return novelty
    except Exception as e:
        logger.warning(
            "[post_recall_trigger] novelty derivation failed: %s — "
            "fallback %.2f", e, FALLBACK_NOVELTY,
        )
        return FALLBACK_NOVELTY


def _derive_receptivity(*, user_id: str) -> float:
    """Rolling receptivity from interject_decisions outcomes in last 24h.

    receptivity = (count_positive + 0.5 * count_neutral) / total
    Outcomes considered: 'positive', 'neutral', 'negative', 'ignored'.
    If fewer than RECEPTIVITY_MIN_SAMPLES outcomes, use FALLBACK_RECEPTIVITY.
    DB failure => LEGACY_RECEPTIVITY (preserves prior hardcoded behaviour).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=RECEPTIVITY_LOOKBACK_HOURS,
    )
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_outcome, COUNT(*) FROM interject_decisions
                WHERE user_id=%s
                  AND decided_at >= %s
                  AND user_outcome IS NOT NULL
                GROUP BY user_outcome
                """,
                (user_id, cutoff),
            )
            counts = {row[0]: int(row[1]) for row in cur.fetchall()}
    except Exception as e:
        logger.warning(
            "[post_recall_trigger] receptivity DB query failed: %s — "
            "fallback %.2f", e, LEGACY_RECEPTIVITY,
        )
        return LEGACY_RECEPTIVITY

    total = sum(counts.values())
    if total < RECEPTIVITY_MIN_SAMPLES:
        logger.info(
            "[post_recall_trigger] receptivity: only %d outcomes in last %dh "
            "(<%d) — fallback %.2f",
            total, RECEPTIVITY_LOOKBACK_HOURS, RECEPTIVITY_MIN_SAMPLES,
            FALLBACK_RECEPTIVITY,
        )
        return FALLBACK_RECEPTIVITY

    pos = counts.get("positive", 0)
    neu = counts.get("neutral", 0)
    raw = (pos + 0.5 * neu) / total
    receptivity = max(0.0, min(1.0, raw))
    logger.info(
        "[post_recall_trigger] receptivity=%.3f from %d outcomes %s",
        receptivity, total, counts,
    )
    return receptivity


def _parse_vector_literal(text: str) -> list[float]:
    """Parse pgvector text form '[1.0,2.0,...]' into a python list."""
    s = text.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    if not s:
        return []
    return [float(x) for x in s.split(",")]
