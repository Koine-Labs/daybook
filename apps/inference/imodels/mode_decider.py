"""Decide Regis's posture (Witness / Companion / Neutral) from runtime context.

Mode is HOW Regis speaks; the interject decider says WHETHER. They compose.

Static moment_kind -> mode mapping (in composer.WITNESS_KINDS / COMPANION_KINDS)
is the default. This module overrides when live user_state_estimate or time-of-day
contradicts the static guess — e.g. a 'walking_remark' fired while user is in REM
flips to witness; an 'rem_whisper' fired when user is clearly awake is downgraded
to neutral so the caller can suppress.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_conn  # noqa: E402


WITNESS_KINDS = {
    "rem_whisper",
    "wake_greeting",
    "capture_ack",
    "sleep_onset_silence",
    "post_recall_reflection",
}
COMPANION_KINDS = {
    "pre_sleep_greeting",
    "intent_setting",
    "morning_recall_prompt",
    "walking_remark",
    "conversation_tease",
    "news_pull_comment",
    "mood_check",
    "chat_message",
}

ASLEEP_REM_PROB = 0.45
AWAKE_REM_PROB = 0.10
STATE_FRESHNESS_SECONDS = 60 * 60


@dataclass
class ModeDecision:
    mode: str
    should_speak: bool
    reason: str
    user_state: dict[str, Any] | None = None
    suggested_kind: str | None = None


def decide_mode(
    *,
    user_id: str,
    moment_kind: str,
    user_state: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> ModeDecision:
    """Decide mode given moment_kind + live user state. Pulls latest state if not provided."""
    if user_state is None:
        user_state = _read_latest_fresh_state(user_id)

    static_mode = _static_mode_for(moment_kind)
    asleep = _is_asleep(user_state)
    awake = _is_awake(user_state)

    if moment_kind == "rem_whisper" and awake:
        return ModeDecision(
            mode="neutral",
            should_speak=False,
            reason="rem_whisper requested but user appears awake; suppress",
            user_state=user_state,
        )

    if static_mode == "companion" and asleep:
        return ModeDecision(
            mode="witness",
            should_speak=False,
            reason=f"companion-kind {moment_kind!r} requested but user asleep; flip to witness, hold",
            user_state=user_state,
            suggested_kind="sleep_onset_silence",
        )

    if static_mode == "witness" and not asleep and moment_kind not in WITNESS_KINDS - {"wake_greeting", "capture_ack"}:
        pass

    if static_mode == "witness":
        return ModeDecision(
            mode="witness",
            should_speak=True,
            reason=f"witness by moment_kind {moment_kind!r}",
            user_state=user_state,
        )

    return ModeDecision(
        mode="companion",
        should_speak=True,
        reason=f"companion by moment_kind {moment_kind!r}",
        user_state=user_state,
    )


def derive_mode_for_chat(user_id: str) -> ModeDecision:
    """Chat-specific shortcut: user is typing, so user is awake unless state strongly disagrees."""
    state = _read_latest_fresh_state(user_id)
    if _is_asleep(state):
        return ModeDecision(
            mode="witness",
            should_speak=True,
            reason="user typed but latest state suggests sleep — speak softly",
            user_state=state,
        )
    return ModeDecision(
        mode="companion",
        should_speak=True,
        reason="user typing → companion",
        user_state=state,
    )


def _static_mode_for(kind: str) -> str:
    if kind in WITNESS_KINDS:
        return "witness"
    if kind in COMPANION_KINDS:
        return "companion"
    return "companion"


def _is_asleep(state: dict[str, Any] | None) -> bool:
    if not state:
        return False
    proba = state.get("stage_proba") or {}
    if not isinstance(proba, dict):
        return False
    rem = float(proba.get("REM", 0.0) or 0.0)
    awake = float(proba.get("AWAKE", 0.0) or 0.0)
    return rem >= ASLEEP_REM_PROB and awake < 0.3


def _is_awake(state: dict[str, Any] | None) -> bool:
    if not state:
        return True
    proba = state.get("stage_proba") or {}
    if not isinstance(proba, dict):
        return True
    rem = float(proba.get("REM", 0.0) or 0.0)
    awake = float(proba.get("AWAKE", 0.0) or 0.0)
    if awake >= 0.5:
        return True
    return rem <= AWAKE_REM_PROB


def _read_latest_fresh_state(user_id: str) -> dict[str, Any] | None:
    cutoff = datetime.now(timezone.utc).timestamp() - STATE_FRESHNESS_SECONDS
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT estimated_at, stage_proba, arousal, valence, presence, confidence, source
            FROM user_state_estimate
            WHERE user_id = %s AND EXTRACT(EPOCH FROM estimated_at) >= %s
            ORDER BY estimated_at DESC
            LIMIT 1
            """,
            (user_id, cutoff),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "estimated_at": row[0].isoformat() if row[0] else None,
        "stage_proba": row[1],
        "arousal": row[2],
        "valence": row[3],
        "presence": row[4],
        "confidence": row[5],
        "source": row[6],
    }
