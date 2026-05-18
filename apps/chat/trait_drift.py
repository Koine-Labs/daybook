"""Heuristic trait-drift rules.

Each rule looks at the user's message (and optionally Regis's reply + prior
session context) and may emit a `TraitDelta`. Deltas are capped per-step and
written to `regis_trait_history` so the latest row per trait reflects current
state.

Trait conventions (see migration 0002):
  - playfulness   — 0.0 reverent, 1.0 chatty/teasing
  - reverence     — 0.0 casual, 1.0 ceremonious
  - chattiness    — 0.0 silent, 1.0 verbose
  - directness    — 0.0 hedged, 1.0 blunt
  - familiarity   — 0.0 formal, 1.0 intimate
  - humor         — 0.0 dry, 1.0 absurd
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import _paths  # noqa: F401
from db import get_conn  # noqa: E402


MAX_DELTA = 0.05
TRAIT_FLOOR = 0.0
TRAIT_CEIL = 1.0
DEFAULT_TRAIT_VALUE = 0.5

KNOWN_TRAITS = {
    "playfulness",
    "reverence",
    "chattiness",
    "directness",
    "familiarity",
    "humor",
}


@dataclass
class TraitDelta:
    trait: str
    delta: float
    reason: str


def maybe_apply_heuristics(
    *,
    user_id: str,
    user_message: str,
    assistant_message: str,
    prior_user_messages: list[str] | None = None,
) -> list[TraitDelta]:
    """Run all rules, write surviving deltas, return them for inspection."""
    prior = prior_user_messages or []
    deltas: list[TraitDelta] = []

    for rule in _RULES:
        try:
            d = rule(user_message, assistant_message, prior)
        except Exception:
            continue
        if d is not None:
            deltas.extend(d if isinstance(d, list) else [d])

    deltas = [_clamp_delta(d) for d in deltas if d.trait in KNOWN_TRAITS]
    for d in deltas:
        _apply(user_id=user_id, delta=d)
    return deltas


def _clamp_delta(d: TraitDelta) -> TraitDelta:
    capped = max(-MAX_DELTA, min(MAX_DELTA, d.delta))
    return TraitDelta(trait=d.trait, delta=capped, reason=d.reason)


def _apply(*, user_id: str, delta: TraitDelta) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT value FROM regis_trait_history
            WHERE user_id = %s AND trait_name = %s
            ORDER BY changed_at DESC LIMIT 1
            """,
            (user_id, delta.trait),
        )
        row = cur.fetchone()
        current = float(row[0]) if row else DEFAULT_TRAIT_VALUE
        new_value = max(TRAIT_FLOOR, min(TRAIT_CEIL, current + delta.delta))
        cur.execute(
            """
            INSERT INTO regis_trait_history
              (user_id, trait_name, value, delta, reason)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, delta.trait, new_value, delta.delta, delta.reason),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


_LAUGH_PAT = re.compile(r"\b(lol|lmao|haha+|hehe+|rofl)\b", re.IGNORECASE)
_THANKS_PAT = re.compile(r"\b(thanks|thank you|appreciate|love it)\b", re.IGNORECASE)
_BREVITY_PAT = re.compile(
    r"\b(shut up|stop|enough|brief|shorter|less|tldr|tl;dr|too long)\b",
    re.IGNORECASE,
)
_INTIMACY_PAT = re.compile(
    r"\b(scared|afraid|alone|lost|hurt|sad|lonely|grief|tired of)\b", re.IGNORECASE
)
_FORMAL_PAT = re.compile(r"\b(please|kindly|would you|could you)\b", re.IGNORECASE)
_BLUNT_PAT = re.compile(r"\b(just tell me|straight|honestly|cut the|stop hedging)\b", re.IGNORECASE)


def _rule_laughter(u: str, _a: str, _p: list[str]) -> TraitDelta | None:
    if _LAUGH_PAT.search(u):
        return TraitDelta("humor", +0.02, "user laughed")
    return None


def _rule_brevity_request(u: str, _a: str, _p: list[str]) -> list[TraitDelta] | None:
    words = u.split()
    if len(words) <= 6 and _BREVITY_PAT.search(u):
        return [
            TraitDelta("chattiness", -0.03, "user asked for brevity"),
            TraitDelta("directness", +0.02, "user asked for brevity"),
        ]
    return None


def _rule_gratitude(u: str, _a: str, _p: list[str]) -> TraitDelta | None:
    if _THANKS_PAT.search(u):
        return TraitDelta("familiarity", +0.01, "user thanked")
    return None


def _rule_vulnerability(u: str, _a: str, _p: list[str]) -> list[TraitDelta] | None:
    if _INTIMACY_PAT.search(u):
        return [
            TraitDelta("reverence", +0.02, "user disclosed vulnerability"),
            TraitDelta("playfulness", -0.02, "user disclosed vulnerability"),
        ]
    return None


def _rule_formality(u: str, _a: str, _p: list[str]) -> TraitDelta | None:
    if _FORMAL_PAT.search(u):
        return TraitDelta("familiarity", -0.01, "user used formal phrasing")
    return None


def _rule_directness(u: str, _a: str, _p: list[str]) -> TraitDelta | None:
    if _BLUNT_PAT.search(u):
        return TraitDelta("directness", +0.03, "user asked for directness")
    return None


def _rule_short_messages_run(_u: str, _a: str, prior: list[str]) -> TraitDelta | None:
    """If the last 3+ user messages average <8 words, dial chattiness down."""
    recent = prior[-3:] if len(prior) >= 3 else []
    if recent and sum(len(m.split()) for m in recent) / len(recent) < 8:
        return TraitDelta("chattiness", -0.01, "user sending consistently short messages")
    return None


def _rule_long_question(u: str, _a: str, _p: list[str]) -> TraitDelta | None:
    """A long, exploratory question invites more speech."""
    if len(u.split()) > 25 and "?" in u:
        return TraitDelta("chattiness", +0.01, "user asked an exploratory question")
    return None


def _rule_emoji_or_caps(u: str, _a: str, _p: list[str]) -> TraitDelta | None:
    """All-caps or shouty punctuation suggests playful energy."""
    if re.search(r"[A-Z]{4,}", u) or u.count("!") >= 2:
        return TraitDelta("playfulness", +0.01, "user wrote with shouty energy")
    return None


_RULES = [
    _rule_laughter,
    _rule_brevity_request,
    _rule_gratitude,
    _rule_vulnerability,
    _rule_formality,
    _rule_directness,
    _rule_short_messages_run,
    _rule_long_question,
    _rule_emoji_or_caps,
]
