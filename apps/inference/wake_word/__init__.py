"""Wake-word + command-intent layer.

WakeEvent is an abstract source — v1.5 uses voice (openWakeWord), v2+ will add
BCI imagined-speech without touching downstream consumers.
"""
from __future__ import annotations

from .command_intent import COMMAND_KEYWORDS, CommandIntent, classify_intent
from .detector import VoiceWakeWordDetector, WakeEvent

__all__ = [
    "WakeEvent",
    "VoiceWakeWordDetector",
    "CommandIntent",
    "COMMAND_KEYWORDS",
    "classify_intent",
]
