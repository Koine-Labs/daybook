"""Daybook chat — text-based interactive conversation with Regis.

Public surface:
  - handle_user_message_streaming(...) -> AsyncIterator[str]   (canonical streaming turn)
  - handle_user_message(...)           -> AssistantResponse    (thin sync wrapper)
  - gather_context(...)                -> dict                 (retrieval bundle)
  - start_or_resume_conversation(...)  -> str                  (conversation_id)
"""
from __future__ import annotations

from .handler import (
    AssistantResponse,
    handle_user_message,
    handle_user_message_streaming,
)
from .retrieval import gather_context
from .conversation import (
    create_conversation,
    most_recent_conversation,
    start_or_resume_conversation,
)

__all__ = [
    "AssistantResponse",
    "handle_user_message",
    "handle_user_message_streaming",
    "gather_context",
    "create_conversation",
    "most_recent_conversation",
    "start_or_resume_conversation",
]
