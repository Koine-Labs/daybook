# apps/inference/output/channels.py
"""Meta-context-aware output channel selection (commitments #3, #14).

Voice (eventual bone-conduction TTS) is the primary surface when the user is
awake (#3). The active meta_context biases L6's channel choice (#14): during
deep sleep no voice/TTS fires — Regis stays silent or, at most, drops to a
non-waking channel. Selection is a small registry of rules + a sentinel for
"no channel" so the layer can have no answer (the silent case).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.protocol.enums import MetaContext

Channel = str  # "voice" | "haptic" | "visual"

# Sentinel: the layer has no waking channel to speak on (e.g. deep sleep).
# Distinct from any real channel so callers branch explicitly on silence.
CHANNEL_SILENT: Channel = "silent"


@dataclass(frozen=True)
class ChannelChoice:
    """A selected channel + delivery pacing biased by the active context."""

    channel: Channel
    delivery: dict[str, object]
    reason: str

    @property
    def is_silent(self) -> bool:
        return self.channel == CHANNEL_SILENT


# Sub-contexts of SLEEP that must never fire voice. meta_context on the
# envelope is the top-level enum; finer sub-state (rem/deep/core/awake-in-bed)
# rides in the value dict when available, so the selector also inspects sub.
_VOICE_SUPPRESSED_SLEEP_SUBSTATES = {"deep", "core", "rem"}


def _waking_voice() -> ChannelChoice:
    return ChannelChoice(
        channel="voice",
        delivery={"pacing": "conversational", "tone_hint": "companion"},
        reason="waking → voice is primary surface (#3)",
    )


def _sleep_choice(substate: str | None) -> ChannelChoice:
    """During sleep, suppress voice; allow a reverent whisper only in light/unknown sub-state."""
    if substate in _VOICE_SUPPRESSED_SLEEP_SUBSTATES:
        return ChannelChoice(
            channel=CHANNEL_SILENT,
            delivery={},
            reason=f"sleep/{substate} → no TTS during deep sleep (#14)",
        )
    # awake-in-bed / light / unknown sub-state: a sparse witness whisper is allowed.
    return ChannelChoice(
        channel="voice",
        delivery={"pacing": "whisper", "tone_hint": "witness", "volume": "low"},
        reason=f"sleep/{substate or 'unknown'} → reverent witness whisper permitted (#5)",
    )


def _unknown_choice() -> ChannelChoice:
    """No confident context → stay silent rather than risk waking-voice over a sleeper."""
    return ChannelChoice(
        channel=CHANNEL_SILENT,
        delivery={},
        reason="meta_context unknown → withhold rather than risk wrong channel",
    )


# Registry: meta_context → selector. Sub-state refines the choice within sleep.
_REGISTRY: dict[MetaContext, Callable[[str | None], ChannelChoice]] = {
    MetaContext.WAKING: lambda _sub: _waking_voice(),
    MetaContext.SLEEP: _sleep_choice,
    MetaContext.UNKNOWN: lambda _sub: _unknown_choice(),
}


def select_channel(meta_context: MetaContext, *, sub_state: str | None = None) -> ChannelChoice:
    """Pick the output channel for the active context (#14); voice primary when waking (#3).

    sub_state is the optional finer sleep/waking tag (e.g. 'deep', 'awake-in-bed').
    Unknown meta_context falls back to silence (fail-safe: never speak over a sleeper).
    """
    selector = _REGISTRY.get(meta_context)
    if selector is None:
        return _unknown_choice()
    return selector(sub_state)
