"""Morning dream-recall capture for Daybook.

Closes the v1 success loop (>=50% improvement in weekly dream recall) by
giving the user a one-tap (or one-line) way to capture dreams immediately
on waking, while the memory trace is still warm.

Public surface:
  - capture(text=..., audio_path=..., record_mic=...) -> DreamCapture
  - DreamCapture dataclass
  - depth_from_text(text) -> 'NONE'|'FRAGMENT'|'SCENE'|'NARRATIVE'
"""

from .capture import DreamCapture, capture, depth_from_text

__all__ = ["DreamCapture", "capture", "depth_from_text"]
