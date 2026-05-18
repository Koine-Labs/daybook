"""Mood capture for Daybook.

Russell's circumplex (valence + arousal in [-1, 1]) plus optional notes.

Public surface:
  - log_mood(user_id, valence, arousal, notes='') -> dict
"""
from __future__ import annotations

from .capture import log_mood

__all__ = ["log_mood"]
