"""Always-on mic capture daemon — VAD-segmented chunk dispatcher."""
from __future__ import annotations

from .listener import AudioChunk, ContinuousMicListener

__all__ = ["AudioChunk", "ContinuousMicListener"]
