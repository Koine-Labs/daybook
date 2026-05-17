from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CueEmission:
    """What the CueEmitter actually delivered. Used for cue_events logging."""
    text: str
    duration_ms: int
    audio_ref: str | None = None  # local file or URL where the audio is saved


class CueEmitter(ABC):
    name: str = "cue"

    @abstractmethod
    def emit(self, text: str, cue_kind: str) -> CueEmission:
        """Deliver the cue. Returns metadata about what was delivered."""
