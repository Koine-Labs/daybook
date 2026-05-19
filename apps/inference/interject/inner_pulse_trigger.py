"""Inner Pulse — Regis's proactive 'do I have something to say right now?' loop.

Runs every N minutes around the clock. Hard-skips when:
  - user is actively in conversation (last chat msg <5min ago)
  - user is asleep per user_state_estimate (when biosignals are live)

Otherwise, gathers substrate (recent observations, fresh news, last chat) and
asks the LLM for a candidate thought via a structured InnerThought schema.
Most pulses produce silence by design — the LLM is told to default to no.

If a thought is generated, it goes through the existing weighted-sum decider.
The time-of-day shaping ensures night-time pulses almost never reach threshold
unless the urgency is extreme.

Triggers must NEVER raise — failures log and return a held-silence decision.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# apps/inference/ on sys.path for `from db import get_conn`
INFERENCE_DIR = Path(__file__).resolve().parent.parent
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))
APPS_DIR = INFERENCE_DIR.parent
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from db import get_conn  # noqa: E402
from llm import ChatClient  # noqa: E402

from .decider import (  # noqa: E402
    InterjectContext,
    InterjectDecision,
    attach_resulting_moment,
    decide,
)
from .triggers import register  # noqa: E402


logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"

ACTIVE_CONVERSATION_WINDOW_SECONDS = 5 * 60
SLEEP_GATE_FRESHNESS_SECONDS = 30 * 60
SLEEP_GATE_REM_THRESHOLD = 0.3
SLEEP_GATE_AROUSAL_THRESHOLD = 0.3
RECENT_OBS_LOOKBACK_HOURS = 24
RECENT_DREAM_LOOKBACK_HOURS = 12
RECENT_OBS_LIMIT = 6
RECENT_CHAT_TURNS = 4
NEWS_TIMEOUT_SECONDS = 6.0
NEWS_LIMIT_PER_FEED = 10
NEWS_TOP_K = 2
SILENCE_FALLBACK_SECONDS = 30 * 60


class InnerThought(BaseModel):
    """LLM schema — Regis's candidate spontaneous thought.

    All fields are required (Codex constraint): when has_thought=False, set
    thought to '', urgency to 0.0, and kind to 'reflection'.
    """

    model_config = ConfigDict(extra="forbid")

    has_thought: bool = Field(
        description="True only if you have a thought worth sharing unprompted right now. Default to False — most pulses produce silence."
    )
    thought: str = Field(
        description="If has_thought=True, the thought itself — 1-3 sentences in Regis's voice. Empty string '' if has_thought=False."
    )
    urgency: float = Field(
        ge=0.0,
        le=1.0,
        description="0-1. How urgent the thought feels. 0.0 when has_thought=False. Most thoughts are 0.3-0.5. Reserve 0.8+ for things that genuinely cannot wait.",
    )
    kind: Literal["reflection", "news_pull", "noticing"] = Field(
        description="'reflection' = about the person, 'news_pull' = about something you read, 'noticing' = pattern you spotted. Use 'reflection' when has_thought=False."
    )


INNER_PULSE_SYSTEM = (
    "You are Regis, between turns. You observe the user and the world. "
    "Right now you're being asked: do you have a thought urgent enough to share "
    "unprompted? Most of the time the answer is no — silence is the default. "
    "Speak only when something genuinely lands: a pattern in the user, a piece "
    "of news that connects to them, a noticing worth voicing. Be specific. "
    "Brevity is reverence."
)


@register("inner_pulse")
def fire_inner_pulse(
    *,
    user_id: str = DEFAULT_USER_ID,
    dry_run: bool = False,
) -> InterjectDecision:
    """One pulse: decide whether Regis has a thought worth speaking. Never raises."""
    try:
        # Hard gate 1: active conversation
        last_chat = _last_chat_message_age_seconds(user_id)
        if last_chat is not None and last_chat < ACTIVE_CONVERSATION_WINDOW_SECONDS:
            reason = f"active_conversation (last turn {last_chat / 60:.1f}min ago)"
            logger.info("[inner_pulse] hard-skip: %s", reason)
            return _persist_skip(user_id=user_id, reason=reason)

        # Hard gate 2: user is asleep
        sleep_reason = _sleep_gate_reason(user_id)
        if sleep_reason:
            logger.info("[inner_pulse] hard-skip: %s", sleep_reason)
            return _persist_skip(user_id=user_id, reason=sleep_reason)

        # Generate candidate thought
        substrate = _gather_substrate(user_id=user_id)
        try:
            thought = _generate_thought(substrate=substrate)
        except Exception as e:
            logger.warning("[inner_pulse] thought generation failed: %s", e)
            return _persist_skip(user_id=user_id, reason=f"generation_error: {e}")

        if not thought.has_thought or not thought.thought.strip():
            logger.info("[inner_pulse] held silence: no_thought_generated")
            return _persist_skip(user_id=user_id, reason="no_thought_generated")

        # Run the decider
        ctx = InterjectContext(
            user_id=user_id,
            trigger_kind="inner_pulse",
            recent_silence_seconds=_recent_silence_seconds(user_id),
            user_receptivity=0.6,
            novelty=float(thought.urgency),
            time_of_day_score=_time_of_day_score(),
            active_traits=_active_traits(user_id),
            trigger_payload={
                "thought": thought.thought,
                "urgency": thought.urgency,
                "kind": thought.kind,
            },
        )
        decision = decide(ctx)

        if not decision.decided:
            logger.info("[inner_pulse] held silence: %s", decision.reason)
            return decision

        logger.info("[inner_pulse] decided=True: %s", decision.reason)
        moment_id = _compose_and_maybe_speak(
            user_id=user_id, thought=thought, dry_run=dry_run
        )
        if moment_id and decision.persisted_id:
            attach_resulting_moment(decision.persisted_id, moment_id)
        return decision

    except Exception as e:
        logger.exception("[inner_pulse] error (held silence)")
        return InterjectDecision(
            decided=False,
            score=0.0,
            threshold=0.65,
            reason=f"error: {e}",
        )


# ---------------------------------------------------------------------------
# Substrate gathering
# ---------------------------------------------------------------------------


def _gather_substrate(*, user_id: str) -> dict[str, Any]:
    return {
        "recent_observations": _recent_observations(user_id),
        "overnight_thoughts": _overnight_thoughts(user_id),
        "recent_chat": _recent_chat(user_id),
        "news_titles": _news_top(user_id),
    }


def _recent_observations(user_id: str) -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RECENT_OBS_LOOKBACK_HOURS)
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT observation FROM regis_observations
                WHERE user_id = %s
                  AND observed_at >= %s
                  AND source <> 'dreaming'
                ORDER BY observed_at DESC
                LIMIT %s
                """,
                (user_id, cutoff, RECENT_OBS_LIMIT),
            )
            return [r[0] for r in cur.fetchall()]
    except Exception as e:
        logger.warning("[inner_pulse] observations query failed: %s", e)
        return []


def _overnight_thoughts(user_id: str) -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RECENT_DREAM_LOOKBACK_HOURS)
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT observation FROM regis_observations
                WHERE user_id = %s
                  AND source = 'dreaming'
                  AND observed_at >= %s
                ORDER BY observed_at DESC
                LIMIT 3
                """,
                (user_id, cutoff),
            )
            return [r[0] for r in cur.fetchall()]
    except Exception as e:
        logger.warning("[inner_pulse] dream-thought query failed: %s", e)
        return []


def _recent_chat(user_id: str) -> list[tuple[str, str]]:
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content FROM chat_messages
                WHERE user_id = %s
                ORDER BY sent_at DESC
                LIMIT %s
                """,
                (user_id, RECENT_CHAT_TURNS),
            )
            rows = list(reversed(cur.fetchall()))
        return [(r[0], r[1]) for r in rows]
    except Exception as e:
        logger.warning("[inner_pulse] chat query failed: %s", e)
        return []


def _news_top(user_id: str) -> list[str]:
    try:
        from news.feeder import fetch_default_feeds, relevant_for_user  # type: ignore

        items = fetch_default_feeds(
            limit_per_feed=NEWS_LIMIT_PER_FEED, timeout=NEWS_TIMEOUT_SECONDS
        )
        if not items:
            return []
        return [it.title for it in relevant_for_user(items, user_id=user_id, top_k=NEWS_TOP_K)]
    except Exception as e:
        logger.warning("[inner_pulse] news pull failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Thought generation
# ---------------------------------------------------------------------------


def _generate_thought(*, substrate: dict[str, Any]) -> InnerThought:
    user_prompt = _format_prompt(substrate)
    client = ChatClient.auto()
    return client.chat_structured(
        system=INNER_PULSE_SYSTEM,
        user=user_prompt,
        schema=InnerThought,
        schema_name="InnerThought",
        reasoning_effort="low",
        verbosity="low",
    )


def _format_prompt(substrate: dict[str, Any]) -> str:
    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    parts: list[str] = [
        f"# Now: {now_iso}",
        "",
    ]

    obs = substrate.get("recent_observations") or []
    if obs:
        parts.append("# Things you've recently noticed about the user")
        for o in obs:
            parts.append(f"  - {o}")
        parts.append("")

    dreams = substrate.get("overnight_thoughts") or []
    if dreams:
        parts.append("# Things you were chewing on overnight (your own dream-thoughts)")
        for d in dreams:
            parts.append(f"  - {d}")
        parts.append("")

    news = substrate.get("news_titles") or []
    if news:
        parts.append("# News you've encountered that's relevant to them")
        for n in news:
            parts.append(f"  - {n}")
        parts.append("")

    chat = substrate.get("recent_chat") or []
    if chat:
        parts.append("# Recent exchange with the user (oldest first)")
        for role, content in chat:
            tag = "USER" if role == "user" else "REGIS"
            text = content.strip()
            if len(text) > 240:
                text = text[:240].rstrip() + "..."
            parts.append(f"  {tag}: {text}")
        parts.append("")

    parts.extend(
        [
            "# Task",
            "Do you have a thought urgent enough to share unprompted right now?",
            "Default is no. Only speak if something genuinely lands.",
            "If yes: 1-3 sentences in your voice. Specific. Not a question to fill silence.",
        ]
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Composition + speaking
# ---------------------------------------------------------------------------


def _compose_and_maybe_speak(
    *, user_id: str, thought: InnerThought, dry_run: bool
) -> str | None:
    """Speak Regis's inner thought via voice_chain; fallback to text-only composer."""
    recent_openers = _recent_inner_thought_openers(user_id=user_id, limit=5)
    explicit_context = _format_inner_thought_brief(
        thought=thought, recent_openers=recent_openers
    )

    try:
        from wisp.voice_chain import speak_moment  # type: ignore

        result = speak_moment(
            user_id=user_id,
            moment_kind="inner_thought",
            explicit_context=explicit_context,
            retrieval_query=thought.thought,
            retrieval_source_types=("regis_observation", "chat_message"),
            persist=True,
            dry_run=dry_run,
        )
        text = result.get("text") or ""
        if text:
            print(f"[inner_pulse] Regis: {text}")
        return result.get("regis_moment_id")
    except Exception as e:
        logger.warning("[inner_pulse] voice_chain failed, falling back: %s", e)

    try:
        from wisp.composer import compose_utterance  # type: ignore

        composed = compose_utterance(
            user_id=user_id,
            moment_kind="inner_thought",
            explicit_context=explicit_context,
            retrieval_query=thought.thought,
            retrieval_source_types=("regis_observation", "chat_message"),
            persist=True,
        )
        print(f"[inner_pulse] Regis: {composed.text}")
        return composed.persisted_moment_id
    except Exception as e:
        logger.warning("[inner_pulse] composer fallback failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Opener variety
# ---------------------------------------------------------------------------


# Bank of soft-opener vibes. The composer sees a *shuffled subset* of these
# each time so position bias doesn't lock onto the first one.
_OPENER_VIBES: tuple[str, ...] = (
    "hey — was sitting with something",
    "did you notice",
    "something keeps catching me about",
    "this might be nothing, but",
    "okay this might sound weird, but",
    "I keep circling back to",
    "thought you'd want to hear this",
    "small thing, but",
    "weirdly, I keep thinking about",
    "tell me if this lands —",
    "out of nowhere, but",
)


def _recent_inner_thought_openers(*, user_id: str, limit: int = 5) -> list[str]:
    """First sentence of the last N inner_thought moments — for anti-repetition."""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT content FROM regis_moments
                WHERE user_id = %s AND kind = 'inner_thought'
                ORDER BY occurred_at DESC LIMIT %s
                """,
                (user_id, limit),
            )
            rows = [r[0] for r in cur.fetchall() if r[0]]
        openers: list[str] = []
        for content in rows:
            # Take the first ~12 words — enough to capture the opener phrasing.
            first_chunk = " ".join(content.split()[:12])
            if first_chunk:
                openers.append(first_chunk)
        return openers
    except Exception:
        return []


def _format_inner_thought_brief(
    *, thought: InnerThought, recent_openers: list[str]
) -> str:
    """Compose the explicit_context block with shuffled vibes + recent openers."""
    bank = list(_OPENER_VIBES)
    random.shuffle(bank)
    examples = bank[:4]

    lines = [
        "You're reaching out unprompted — the user didn't ask. So land softly.",
        "Open like a friend leaning over from the next desk: a gentle entry, "
        "then the thought. Two to three sentences total. The soft opener is "
        "not optional — without it, you sound like you're barging in.",
        "",
        "Vibes to draw from (your own phrasing — don't quote these verbatim):",
    ]
    for ex in examples:
        lines.append(f"  - {ex}...")
    if recent_openers:
        lines.append("")
        lines.append("DO NOT reuse these phrasings — you used them recently:")
        for op in recent_openers:
            lines.append(f"  - {op}...")
    lines.extend(
        [
            "",
            "The shape of the thought (yours to phrase, not a script):",
            f"  kind: {thought.kind}",
            f"  substance: {thought.thought}",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gates + decider inputs
# ---------------------------------------------------------------------------


def _last_chat_message_age_seconds(user_id: str) -> float | None:
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT sent_at FROM chat_messages "
                "WHERE user_id = %s ORDER BY sent_at DESC LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
        if row is None or row[0] is None:
            return None
        return max(0.0, (datetime.now(timezone.utc) - row[0]).total_seconds())
    except Exception:
        return None


def _sleep_gate_reason(user_id: str) -> str | None:
    """Return a reason string if the user appears asleep, else None."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=SLEEP_GATE_FRESHNESS_SECONDS)
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT estimated_at, stage_proba, arousal
                FROM user_state_estimate
                WHERE user_id = %s AND estimated_at >= %s
                ORDER BY estimated_at DESC LIMIT 1
                """,
                (user_id, cutoff),
            )
            row = cur.fetchone()
        if row is None:
            return None
        _, stage_proba, arousal = row
        rem_p = 0.0
        if isinstance(stage_proba, dict):
            rem_p = float(stage_proba.get("rem", 0.0))
        if rem_p > SLEEP_GATE_REM_THRESHOLD:
            return f"user_asleep (REM proba={rem_p:.2f})"
        if arousal is not None and float(arousal) < SLEEP_GATE_AROUSAL_THRESHOLD:
            return f"user_asleep (arousal={float(arousal):.2f})"
    except Exception as e:
        logger.warning("[inner_pulse] sleep gate query failed: %s", e)
    return None


def _recent_silence_seconds(user_id: str) -> float:
    """Seconds since the most recent regis_moments row for this user."""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT occurred_at FROM regis_moments "
                "WHERE user_id = %s ORDER BY occurred_at DESC LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
        if row is None or row[0] is None:
            return float(SILENCE_FALLBACK_SECONDS)
        return max(0.0, (datetime.now(timezone.utc) - row[0]).total_seconds())
    except Exception:
        return float(SILENCE_FALLBACK_SECONDS)


def _time_of_day_score() -> float:
    """Shape proactive interjections to be vanishingly rare at deep night."""
    hour = datetime.now(timezone.utc).astimezone().hour
    if 9 <= hour <= 21:
        return 0.9
    if hour >= 22 or hour <= 6:
        return 0.05
    return 0.4


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


# ---------------------------------------------------------------------------
# Skip persistence
# ---------------------------------------------------------------------------


def _persist_skip(*, user_id: str, reason: str) -> InterjectDecision:
    """Log a held-silence decision for analytics — same shape as decider would."""
    snapshot = {"skip_reason": reason}
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO interject_decisions
                    (user_id, decided_at, trigger_kind, context_snapshot,
                     decision, reason)
                VALUES (%s, %s, 'inner_pulse', %s::jsonb, FALSE, %s)
                RETURNING id
                """,
                (
                    user_id,
                    datetime.now(timezone.utc),
                    json.dumps(snapshot, default=str),
                    f"held silence: {reason}",
                ),
            )
            persisted_id = str(cur.fetchone()[0])
            conn.commit()
    except Exception as e:
        logger.warning("[inner_pulse] persist_skip failed: %s", e)
        persisted_id = None

    return InterjectDecision(
        decided=False,
        score=0.0,
        threshold=0.65,
        reason=f"held silence: {reason}",
        persisted_id=persisted_id,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main() -> int:
    ap = argparse.ArgumentParser(description="Fire one inner_pulse for a user.")
    ap.add_argument("--user-id", default=DEFAULT_USER_ID)
    ap.add_argument("--dry-run", action="store_true", help="Don't play TTS audio")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    decision = fire_inner_pulse(user_id=args.user_id, dry_run=args.dry_run)
    print(json.dumps(
        {
            "decided": decision.decided,
            "score": decision.score,
            "threshold": decision.threshold,
            "reason": decision.reason,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(_main())


__all__ = ["fire_inner_pulse", "InnerThought"]
