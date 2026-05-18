"""Command-vs-message intent classifier for utterances captured post-wake.

v0: keyword matching with strict short-utterance gating. v1 will replace this
with an LLM classifier; the public surface stays stable.
"""
from __future__ import annotations

import re
from enum import Enum


class CommandIntent(str, Enum):
    LISTEN = "listen"
    SEE = "see"
    DISMISS = "dismiss"
    ACKNOWLEDGE = "acknowledge"
    SCRATCH_THAT = "scratch"
    NONE = "none"


COMMAND_KEYWORDS: dict[CommandIntent, list[str]] = {
    CommandIntent.LISTEN: ["listen", "pay attention", "hear this", "hear that"],
    CommandIntent.SEE: ["look", "see", "check this out", "see this", "look at this"],
    CommandIntent.DISMISS: [
        "shut up",
        "stop",
        "be quiet",
        "silence",
        "dismiss",
        "go away",
        "nevermind",
    ],
    CommandIntent.ACKNOWLEDGE: [
        "go on",
        "continue",
        "yes",
        "yeah",
        "uh huh",
        "mhm",
        "right",
    ],
    CommandIntent.SCRATCH_THAT: [
        "scratch that",
        "never mind",
        "cancel",
        "forget it",
        "forget that",
    ],
}

MAX_COMMAND_WORDS = 6


def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^\w\s'-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _word_count(text: str) -> int:
    return len(text.split()) if text else 0


def classify_intent(text: str) -> CommandIntent:
    """Return the command intent, or NONE if the utterance should be treated as a message.

    Conservative: only fires as a command if the utterance is short (<= 6 words)
    AND contains a keyword phrase as a whole-word match. Longer utterances always
    fall through to NONE so they get routed to chat.
    """
    norm = _normalize(text)
    if not norm:
        return CommandIntent.NONE

    if _word_count(norm) > MAX_COMMAND_WORDS:
        return CommandIntent.NONE

    padded = f" {norm} "
    for intent, phrases in COMMAND_KEYWORDS.items():
        for phrase in phrases:
            candidate = f" {phrase} "
            if candidate in padded:
                return intent
    return CommandIntent.NONE


__all__ = [
    "CommandIntent",
    "COMMAND_KEYWORDS",
    "MAX_COMMAND_WORDS",
    "classify_intent",
]
