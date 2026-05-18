"""Intent capture for Daybook.

Pre-sleep (or any-time) intent setting. The user says what they want to
focus on, remember, dream about, or carry forward into the next session.

Public surface:
  - set_intent(user_id, text, target_session_id=None) -> dict
"""
from __future__ import annotations

from .capture import set_intent

__all__ = ["set_intent"]
