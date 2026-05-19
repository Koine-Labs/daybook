"""Scheduled pre-sleep trigger.

Fires ~22:30 local. Composes a short reminder gently steering the user toward
intent-setting and brief day reflection. Mode shades from companion toward
witness as the day winds down.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

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

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
RECENT_OBS_LIMIT = 2


@dataclass
class PreSleepSections:
    intent_today: str | None
    recent_observations: list[str]
    last_sleep_summary: str | None


@register("pre_sleep")
def fire_pre_sleep(
    *,
    user_id: str = DEFAULT_USER_ID,
    dry_run: bool = False,
) -> InterjectDecision:
    """Compose (and optionally speak) the pre-sleep reminder. Never raises."""
    try:
        sections = _gather_sections(user_id=user_id)
        explicit_context = _format_context(sections)

        ctx = InterjectContext(
            user_id=user_id,
            trigger_kind="pre_sleep",
            recent_silence_seconds=_recent_silence_seconds(user_id),
            user_receptivity=0.75,
            novelty=0.6,
            time_of_day_score=_time_of_day_score(),
            active_traits=_active_traits(user_id),
            trigger_payload={
                "intent_today": sections.intent_today,
                "recent_observations": sections.recent_observations,
                "last_sleep_summary": sections.last_sleep_summary,
            },
        )

        decision = decide(ctx)

        if decision.decided:
            moment_id = _compose_and_maybe_speak(
                user_id=user_id,
                explicit_context=explicit_context,
                dry_run=dry_run,
            )
            if moment_id and decision.persisted_id:
                attach_resulting_moment(decision.persisted_id, moment_id)

        return decision
    except Exception as e:
        print(f"[pre_sleep_trigger] error (held silence): {e}")
        return InterjectDecision(
            decided=False,
            score=0.0,
            threshold=0.65,
            reason=f"error: {e}",
        )


def compose_pre_sleep_text(
    *,
    user_id: str = DEFAULT_USER_ID,
    persist: bool = False,
) -> dict[str, Any]:
    """Compose the pre-sleep text without the decider (smoke + manual)."""
    sections = _gather_sections(user_id=user_id)
    explicit_context = _format_context(sections)

    from wisp.composer import compose_utterance  # type: ignore

    composed = compose_utterance(
        user_id=user_id,
        moment_kind="pre_sleep_prompt",
        explicit_context=explicit_context,
        retrieval_query=explicit_context,
        retrieval_source_types=("intent", "dream_recall", "regis_observation"),
        persist=persist,
    )
    return {
        "text": composed.text,
        "mode": composed.mode,
        "sections": {
            "intent_today": sections.intent_today,
            "recent_observations": sections.recent_observations,
            "last_sleep_summary": sections.last_sleep_summary,
        },
        "persisted_moment_id": composed.persisted_moment_id,
    }


# ---------------------------------------------------------------------------
# Section gatherers
# ---------------------------------------------------------------------------


def _gather_sections(*, user_id: str) -> PreSleepSections:
    return PreSleepSections(
        intent_today=_today_intent(user_id),
        recent_observations=_recent_observations(user_id),
        last_sleep_summary=_last_sleep_brief(user_id),
    )


def _today_intent(user_id: str) -> str | None:
    """Most recent intent set today (local-day window)."""
    local_now = datetime.now(timezone.utc).astimezone()
    local_midnight = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
    cutoff_utc = local_midnight.astimezone(timezone.utc)
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT intent_text FROM intents
                WHERE user_id = %s
                  AND set_at >= %s
                ORDER BY set_at DESC
                LIMIT 1
                """,
                (user_id, cutoff_utc),
            )
            row = cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        print(f"[pre_sleep] intent query failed: {e}")
        return None


def _recent_observations(user_id: str) -> list[str]:
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT observation FROM regis_observations
                WHERE user_id = %s
                ORDER BY observed_at DESC
                LIMIT %s
                """,
                (user_id, RECENT_OBS_LIMIT),
            )
            return [r[0] for r in cur.fetchall()]
    except Exception as e:
        print(f"[pre_sleep] observation query failed: {e}")
        return []


def _last_sleep_brief(user_id: str) -> str | None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=36)
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT duration_seconds FROM sleep_sessions
                WHERE user_id = %s AND started_at >= %s
                ORDER BY started_at DESC LIMIT 1
                """,
                (user_id, cutoff),
            )
            row = cur.fetchone()
        if row is None:
            return None
        hours = (row[0] or 0) / 3600.0
        return f"{hours:.1f}h last night"
    except Exception:
        return None


def _format_context(sections: PreSleepSections) -> str:
    parts: list[str] = [
        "It's late evening. User is heading toward sleep.",
        "Compose 2-3 sentences. Tone: warm, low, beginning to shade from companion to witness.",
        "Gently surface whether an intent was set (don't lecture if not).",
        "Offer a small thread for them to follow into the night — one question or one notice. No verdicts.",
        "",
    ]
    if sections.intent_today:
        parts.append(f"Intent set today: \"{sections.intent_today}\"")
    else:
        parts.append("Intent set today: (none yet)")
    if sections.last_sleep_summary:
        parts.append(f"Previous night's duration: {sections.last_sleep_summary}")
    if sections.recent_observations:
        parts.append("Recent observations:")
        for o in sections.recent_observations:
            parts.append(f"  - {o}")
    return "\n".join(parts)


def _compose_and_maybe_speak(
    *,
    user_id: str,
    explicit_context: str,
    dry_run: bool,
) -> str | None:
    try:
        from wisp.voice_chain import speak_moment  # type: ignore
        try:
            result = speak_moment(
                user_id=user_id,
                moment_kind="pre_sleep_prompt",
                explicit_context=explicit_context,
                retrieval_query=explicit_context,
                retrieval_source_types=("intent", "dream_recall", "regis_observation"),
                persist=True,
                dry_run=dry_run,
            )
            text = result.get("text") or ""
            if text:
                print(f"[pre_sleep] Regis: {text}")
            return result.get("regis_moment_id")
        except Exception as e:
            print(f"[pre_sleep] voice_chain failed, falling back: {e}")
    except ImportError:
        pass

    try:
        from wisp.composer import compose_utterance  # type: ignore
        composed = compose_utterance(
            user_id=user_id,
            moment_kind="pre_sleep_prompt",
            explicit_context=explicit_context,
            retrieval_query=explicit_context,
            retrieval_source_types=("intent", "dream_recall", "regis_observation"),
            persist=True,
        )
        print(f"[pre_sleep] Regis: {composed.text}")
        return composed.persisted_moment_id
    except Exception as e:
        print(f"[pre_sleep] composer failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Decider inputs
# ---------------------------------------------------------------------------


def _recent_silence_seconds(user_id: str) -> float:
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT occurred_at FROM regis_moments "
                "WHERE user_id=%s ORDER BY occurred_at DESC LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
        if row is None or row[0] is None:
            return float(60 * 60)
        delta = datetime.now(timezone.utc) - row[0]
        return max(0.0, delta.total_seconds())
    except Exception:
        return float(60 * 60)


def _time_of_day_score() -> float:
    hour = datetime.now(timezone.utc).astimezone().hour
    if 21 <= hour <= 23:
        return 0.9
    if hour == 0 or hour == 20:
        return 0.7
    return 0.4


def _active_traits(user_id: str) -> dict[str, float]:
    """Latest signal-sourced value per trait. Excludes baseline/decay rows.

    Delegates to chat.baseline_computer.fetch_current_trait_values — see
    CURRENT_VALUE_SOURCE_FILTER for the rationale.
    """
    try:
        from chat.baseline_computer import fetch_current_trait_values  # type: ignore
        return fetch_current_trait_values(user_id)
    except Exception:
        return {}


__all__ = ["fire_pre_sleep", "compose_pre_sleep_text"]
