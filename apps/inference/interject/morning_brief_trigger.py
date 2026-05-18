"""Scheduled morning-brief trigger.

Fires ~07:30 local. Composes a 2-4 sentence brief covering:
  - last night's sleep (sleep_observer recent obs preferred, else basic stats)
  - top 1-2 user-relevant news items (best-effort RSS pull)
  - most recent 1-2 regis_observations

Goes through the auto-interject decider with a high default receptivity (the
user just woke up; a quiet 2-line brief is expected). On decided=True the
composer assembles the utterance; speaks via voice_chain if available.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
SLEEP_LOOKBACK_HOURS = 16
NEWS_TIMEOUT_SECONDS = 8.0
NEWS_LIMIT_PER_FEED = 12
NEWS_TOP_K = 2
RECENT_OBS_LIMIT = 2


@dataclass
class MorningBriefSections:
    sleep: str
    news: list[str]
    observations: list[str]


@register("morning_brief")
def fire_morning_brief(
    *,
    user_id: str = DEFAULT_USER_ID,
    target_time_minutes_after_wake: int = 0,
    dry_run: bool = False,
) -> InterjectDecision:
    """Compose (and optionally speak) the morning brief. Never raises."""
    try:
        sections = _gather_sections(user_id=user_id)
        explicit_context = _format_context(sections)

        ctx = InterjectContext(
            user_id=user_id,
            trigger_kind="morning_brief",
            recent_silence_seconds=_recent_silence_seconds(user_id),
            user_receptivity=0.8,
            novelty=0.7,
            time_of_day_score=_time_of_day_score(),
            active_traits=_active_traits(user_id),
            trigger_payload={
                "target_time_minutes_after_wake": target_time_minutes_after_wake,
                "sleep": sections.sleep,
                "news_titles": sections.news,
                "observations": sections.observations,
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
        print(f"[morning_brief_trigger] error (held silence): {e}")
        return InterjectDecision(
            decided=False,
            score=0.0,
            threshold=0.65,
            reason=f"error: {e}",
        )


def compose_morning_brief_text(
    *,
    user_id: str = DEFAULT_USER_ID,
    persist: bool = False,
) -> dict[str, Any]:
    """Compose the brief text without going through the decider (smoke + manual)."""
    sections = _gather_sections(user_id=user_id)
    explicit_context = _format_context(sections)

    from wisp.composer import compose_utterance  # type: ignore

    composed = compose_utterance(
        user_id=user_id,
        moment_kind="morning_brief",
        explicit_context=explicit_context,
        retrieval_query=explicit_context,
        retrieval_source_types=("regis_observation", "dream_recall"),
        persist=persist,
    )
    return {
        "text": composed.text,
        "mode": composed.mode,
        "sections": {
            "sleep": sections.sleep,
            "news": sections.news,
            "observations": sections.observations,
        },
        "persisted_moment_id": composed.persisted_moment_id,
    }


# ---------------------------------------------------------------------------
# Section gatherers
# ---------------------------------------------------------------------------


def _gather_sections(*, user_id: str) -> MorningBriefSections:
    return MorningBriefSections(
        sleep=_sleep_summary(user_id),
        news=_news_top(user_id),
        observations=_recent_observations(user_id),
    )


def _sleep_summary(user_id: str) -> str:
    """Best-effort: recent sleep_observer observations, else basic session stats."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=SLEEP_LOOKBACK_HOURS)
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT observation FROM regis_observations
                WHERE user_id = %s
                  AND source = 'sleep_observer'
                  AND observed_at >= %s
                ORDER BY observed_at DESC
                LIMIT 2
                """,
                (user_id, cutoff),
            )
            rows = [r[0] for r in cur.fetchall()]
        if rows:
            return " ".join(rows)
    except Exception as e:
        print(f"[morning_brief] sleep_observer query failed: {e}")

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT started_at, ended_at, duration_seconds
                FROM sleep_sessions
                WHERE user_id = %s
                  AND started_at >= %s
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (user_id, cutoff),
            )
            row = cur.fetchone()
        if row is None:
            return "no session logged last night"
        started, ended, dur = row
        hours = (dur or 0) / 3600.0
        return (
            f"slept {hours:.1f}h ({started.strftime('%H:%M')}–{ended.strftime('%H:%M')})"
        )
    except Exception as e:
        print(f"[morning_brief] sleep_sessions query failed: {e}")
        return "no session logged last night"


def _news_top(user_id: str) -> list[str]:
    """Best-effort relevant news titles. Returns [] on any failure."""
    try:
        from news.feeder import (  # type: ignore
            fetch_default_feeds,
            relevant_for_user,
        )
        items = fetch_default_feeds(
            limit_per_feed=NEWS_LIMIT_PER_FEED,
            timeout=NEWS_TIMEOUT_SECONDS,
        )
        if not items:
            return []
        filtered = relevant_for_user(items, user_id=user_id, top_k=NEWS_TOP_K)
        return [it.title for it in filtered]
    except Exception as e:
        print(f"[morning_brief] news pull failed (skipping): {e}")
        return []


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
        print(f"[morning_brief] observation query failed: {e}")
        return []


def _format_context(sections: MorningBriefSections) -> str:
    parts: list[str] = [
        "User just woke up. Deliver a 2-4 sentence morning brief.",
        "Texture it; do not list. Mention sleep, one relevant news beat if it lands, "
        "and any pattern you've noticed. Speak as if checking in over the first sip of coffee.",
        "",
        f"Last night's sleep: {sections.sleep or '(unknown)'}",
    ]
    if sections.news:
        parts.append("Relevant news today:")
        for t in sections.news:
            parts.append(f"  - {t}")
    else:
        parts.append("News: (no relevant beats today)")
    if sections.observations:
        parts.append("Recent things you've noticed about them:")
        for o in sections.observations:
            parts.append(f"  - {o}")
    return "\n".join(parts)


def _compose_and_maybe_speak(
    *,
    user_id: str,
    explicit_context: str,
    dry_run: bool,
) -> str | None:
    """Speak via voice_chain if present; else text-only composer fallback."""
    try:
        from wisp.voice_chain import speak_moment  # type: ignore
        try:
            result = speak_moment(
                user_id=user_id,
                moment_kind="morning_brief",
                explicit_context=explicit_context,
                retrieval_query=explicit_context,
                retrieval_source_types=("regis_observation", "dream_recall"),
                persist=True,
                dry_run=dry_run,
            )
            text = result.get("text") or ""
            if text:
                print(f"[morning_brief] Regis: {text}")
            return result.get("regis_moment_id")
        except Exception as e:
            print(f"[morning_brief] voice_chain failed, falling back: {e}")
    except ImportError:
        pass

    try:
        from wisp.composer import compose_utterance  # type: ignore
        composed = compose_utterance(
            user_id=user_id,
            moment_kind="morning_brief",
            explicit_context=explicit_context,
            retrieval_query=explicit_context,
            retrieval_source_types=("regis_observation", "dream_recall"),
            persist=True,
        )
        print(f"[morning_brief] Regis: {composed.text}")
        return composed.persisted_moment_id
    except Exception as e:
        print(f"[morning_brief] composer failed: {e}")
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
    if 6 <= hour <= 10:
        return 0.9
    if 5 <= hour <= 11:
        return 0.75
    return 0.5


def _active_traits(user_id: str) -> dict[str, float]:
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


__all__ = ["fire_morning_brief", "compose_morning_brief_text"]
