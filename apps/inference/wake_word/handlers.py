"""Handlers for each command intent — all write to user_actions.

Handlers NEVER raise; they log + return a graceful default result so the mic
loop stays alive.

Each handler returns a dict shape:
    {"ok": bool, "ack": str, "action_id": str | None, "intent": str, "error": str | None}

`ack` is what Regis should optionally say back. Empty string means stay silent.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

APPS_DIR = Path(__file__).resolve().parent.parent.parent
INFERENCE_DIR = APPS_DIR / "inference"
for _p in (APPS_DIR, INFERENCE_DIR):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from db import get_conn  # noqa: E402
from gesture.recorder import record_action  # noqa: E402

from .command_intent import CommandIntent  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_DISMISS_MINUTES = 5
SOURCE = "voice_command"


def _ok(intent: CommandIntent, action_id: str | None, ack: str) -> dict:
    return {
        "ok": True,
        "ack": ack,
        "action_id": action_id,
        "intent": intent.value,
        "error": None,
    }


def _err(intent: CommandIntent, exc: Exception) -> dict:
    logger.exception("handler for %s failed", intent.value)
    return {
        "ok": False,
        "ack": "",
        "action_id": None,
        "intent": intent.value,
        "error": str(exc),
    }


def _record(intent: CommandIntent, *, user_id: str, context: dict) -> str | None:
    try:
        return record_action(
            user_id=user_id,
            kind="voice_command",
            source=SOURCE,
            intent=intent.value,
            context=context,
        )
    except Exception:
        logger.exception("record_action failed for %s", intent.value)
        return None


def handle_listen(*, user_id: str, context: dict | None = None) -> dict:
    """Escalate audio-context attention. v0: log to user_actions + ack."""
    intent = CommandIntent.LISTEN
    try:
        ctx = dict(context or {})
        ctx.setdefault("escalation", "audio_attention")
        action_id = _record(intent, user_id=user_id, context=ctx)
        return _ok(intent, action_id, "Listening.")
    except Exception as e:
        return _err(intent, e)


def handle_see(*, user_id: str, context: dict | None = None) -> dict:
    """Escalate visual-context attention. v0: log to user_actions + ack."""
    intent = CommandIntent.SEE
    try:
        ctx = dict(context or {})
        ctx.setdefault("escalation", "visual_attention")
        action_id = _record(intent, user_id=user_id, context=ctx)
        return _ok(intent, action_id, "Looking.")
    except Exception as e:
        return _err(intent, e)


def handle_dismiss(
    *,
    user_id: str,
    context: dict | None = None,
    silence_minutes: int = DEFAULT_DISMISS_MINUTES,
) -> dict:
    """Set silenced flag for next N minutes. v0: log to user_actions."""
    intent = CommandIntent.DISMISS
    try:
        ctx = dict(context or {})
        until = datetime.now(timezone.utc) + timedelta(minutes=silence_minutes)
        ctx.setdefault("silenced_until", until.isoformat())
        ctx.setdefault("silence_minutes", silence_minutes)
        action_id = _record(intent, user_id=user_id, context=ctx)
        return _ok(intent, action_id, "")
    except Exception as e:
        return _err(intent, e)


def handle_acknowledge(*, user_id: str, context: dict | None = None) -> dict:
    """Gesture-style ack from voice. v0: log to user_actions."""
    intent = CommandIntent.ACKNOWLEDGE
    try:
        ctx = dict(context or {})
        action_id = _record(intent, user_id=user_id, context=ctx)
        return _ok(intent, action_id, "")
    except Exception as e:
        return _err(intent, e)


def handle_scratch_that(*, user_id: str, context: dict | None = None) -> dict:
    """Mark the last regis_moments row as retracted; log to user_actions."""
    intent = CommandIntent.SCRATCH_THAT
    retracted_id: str | None = None
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM regis_moments
                WHERE user_id = %s
                ORDER BY occurred_at DESC NULLS LAST
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if row:
                retracted_id = str(row[0])
                cur.execute(
                    """
                    UPDATE regis_moments
                    SET payload = COALESCE(payload, '{}'::jsonb)
                                  || jsonb_build_object('retracted', true,
                                                        'retracted_at', %s)
                    WHERE id = %s
                    """,
                    (datetime.now(timezone.utc).isoformat(), retracted_id),
                )
                conn.commit()
    except Exception:
        logger.exception("scratch_that: failed to mark last moment retracted (continuing)")

    try:
        ctx = dict(context or {})
        if retracted_id:
            ctx.setdefault("retracted_moment_id", retracted_id)
        action_id = _record(intent, user_id=user_id, context=ctx)
        return _ok(intent, action_id, "Scratched.")
    except Exception as e:
        return _err(intent, e)


INTENT_HANDLERS = {
    CommandIntent.LISTEN: handle_listen,
    CommandIntent.SEE: handle_see,
    CommandIntent.DISMISS: handle_dismiss,
    CommandIntent.ACKNOWLEDGE: handle_acknowledge,
    CommandIntent.SCRATCH_THAT: handle_scratch_that,
}


def dispatch(intent: CommandIntent, *, user_id: str, context: dict | None = None) -> dict:
    """Route an intent to its handler. Returns the handler dict (NEVER raises)."""
    handler = INTENT_HANDLERS.get(intent)
    if handler is None:
        return {
            "ok": False,
            "ack": "",
            "action_id": None,
            "intent": intent.value if isinstance(intent, CommandIntent) else str(intent),
            "error": "no handler",
        }
    try:
        return handler(user_id=user_id, context=context)
    except Exception as e:
        return _err(intent, e)


__all__ = [
    "handle_listen",
    "handle_see",
    "handle_dismiss",
    "handle_acknowledge",
    "handle_scratch_that",
    "dispatch",
    "INTENT_HANDLERS",
]
