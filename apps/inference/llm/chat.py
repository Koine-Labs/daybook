"""Unified ChatClient interface — routes to Codex (signed-in) or Gateway (API key).

Higher-level Daybook code calls this; it should not need to know which backend
is active.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import AsyncIterator, Type, TypeVar

from pydantic import BaseModel

from .auth.session import get_sign_in_status
from .codex_client import (
    call_codex_stream,
    call_codex_structured,
    call_codex_text,
)


# Default Codex model used by funda — same default here for consistency.
DEFAULT_CODEX_MODEL = os.environ.get("DAYBOOK_CODEX_MODEL", "gpt-5.2")
DEFAULT_GATEWAY_MODEL = os.environ.get(
    "DAYBOOK_GATEWAY_MODEL", "anthropic/claude-sonnet-4-6"
)

T = TypeVar("T", bound=BaseModel)


@dataclass
class ChatClient:
    """Routed LLM client. Use `ChatClient.auto()` to construct."""

    backend: str  # 'codex' | 'gateway'
    model: str

    @classmethod
    def auto(cls, *, prefer: str | None = None) -> "ChatClient":
        """Pick Codex if signed in, else Gateway.

        `prefer` can force a backend ('codex' or 'gateway') for testing.
        """
        if prefer == "codex" or (prefer is None and get_sign_in_status().signed_in):
            return cls(backend="codex", model=DEFAULT_CODEX_MODEL)
        if prefer == "gateway" or prefer is None:
            return cls(backend="gateway", model=DEFAULT_GATEWAY_MODEL)
        raise ValueError(f"Unknown backend preference: {prefer}")

    def chat(
        self,
        *,
        system: str,
        user: str,
        reasoning_effort: str = "medium",
        verbosity: str = "medium",
    ) -> str:
        """Free-form text response."""
        if self.backend == "codex":
            res = call_codex_text(
                system=system,
                user=user,
                model=self.model,
                reasoning_effort=reasoning_effort,
                verbosity=verbosity,
            )
            return res.text
        raise NotImplementedError(
            f"Gateway backend not yet implemented (model={self.model}). "
            "Sign in with ChatGPT via `python -m llm.auth.sign_in` to use Codex."
        )

    async def chat_stream(
        self,
        *,
        system: str,
        user: str,
        reasoning_effort: str = "low",
        verbosity: str = "low",
    ) -> AsyncIterator[str]:
        """Yields tokens as they arrive. Codex backend only; Gateway raises."""
        if self.backend == "codex":
            async for delta in call_codex_stream(
                system=system,
                user=user,
                model=self.model,
                reasoning_effort=reasoning_effort,
                verbosity=verbosity,
            ):
                yield delta
            return
        raise NotImplementedError(
            "Streaming not yet implemented for Gateway backend"
        )

    def chat_structured(
        self,
        *,
        system: str,
        user: str,
        schema: Type[T],
        schema_name: str | None = None,
        reasoning_effort: str = "medium",
        verbosity: str = "medium",
    ) -> T:
        """JSON-schema-constrained response, parsed back into a Pydantic model."""
        if self.backend == "codex":
            res = call_codex_structured(
                system=system,
                user=user,
                model=self.model,
                schema_model=schema,
                schema_name=schema_name,
                reasoning_effort=reasoning_effort,
                verbosity=verbosity,
            )
            return res.data  # type: ignore[return-value]
        raise NotImplementedError(
            f"Gateway backend not yet implemented (model={self.model})."
        )
