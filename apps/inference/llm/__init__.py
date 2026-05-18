"""LLM interaction layer for Daybook.

Two backends:
  - Codex (chatgpt.com/backend-api/codex/responses) via OAuth-with-ChatGPT
    — uses your ChatGPT Plus/Pro subscription; zero incremental cost per call.
  - Gateway fallback (Vercel AI Gateway / direct API) — when no ChatGPT auth
    is available; uses an API key.

Provider routing happens in `chat.ChatClient.auto()`. Daybook code at higher
layers should not care which backend is active.
"""

from .chat import ChatClient

__all__ = ["ChatClient"]
