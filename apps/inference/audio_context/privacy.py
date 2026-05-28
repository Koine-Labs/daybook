"""Privacy Policy #1 — pause-on-other-voice. Pure, testable state machine."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

DEFAULT_BUFFER_SECONDS = 30.0


@dataclass
class GateDecision:
    social_context: str          # 'self' | 'other' | 'both' | 'none'
    allow_prosody: bool
    allow_ambient: bool
    allow_stt: bool
    suppressed_until: datetime | None


class PrivacyGate:
    """Tracks a suppression deadline. 'unknown' speakers count as 'other'."""

    def __init__(self, *, buffer_seconds: float = DEFAULT_BUFFER_SECONDS) -> None:
        self.buffer_seconds = buffer_seconds
        self._suppressed_until: datetime | None = None

    def _classify(self, speakers: list[str]) -> str:
        has_self = "self" in speakers
        has_other = any(s in ("other", "unknown") for s in speakers)
        if has_self and has_other:
            return "both"
        if has_other:
            return "other"
        if has_self:
            return "self"
        return "none"

    def evaluate(self, *, speakers: list[str], now: datetime) -> GateDecision:
        social = self._classify(speakers)

        if social in ("other", "both"):
            self._suppressed_until = now + timedelta(seconds=self.buffer_seconds)

        suppressed = self._suppressed_until is not None and now < self._suppressed_until

        # Prosody only on voiced self-speech that isn't suppressed.
        allow_prosody = (social == "self") and not suppressed
        # Ambient runs during non-suppressed silence/self windows.
        allow_ambient = (social in ("self", "none")) and not suppressed
        allow_stt = (social in ("self", "none")) and not suppressed

        return GateDecision(
            social_context=social,
            allow_prosody=allow_prosody,
            allow_ambient=allow_ambient,
            allow_stt=allow_stt,
            suppressed_until=self._suppressed_until,
        )
