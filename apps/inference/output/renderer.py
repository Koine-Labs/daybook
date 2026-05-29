# apps/inference/output/renderer.py
"""Render an ActionDecision into utterance text for an OutputDirective.

The real renderer wraps apps/wisp/composer.py::compose_utterance (persona +
state + retrieval → LLM). That path calls the network, so it is NOT exercised
by tests. The renderer is injectable: tests pass `StubRenderer`, which returns
deterministic placeholder text with no network/LLM call. Real composer wiring
is a later fill (see spec §5: composer relocates into output/).
"""
from __future__ import annotations

from typing import Protocol

from core.protocol.payloads import ActionDecision


class Renderer(Protocol):
    """Turns a chosen action + mode into utterance text."""

    def render(self, decision: ActionDecision, *, mode: str | None) -> str: ...


class StubRenderer:
    """Deterministic placeholder renderer — no LLM, safe for tests and offline runs.

    Returns honest placeholder text (never fabricated, clearly marked) so the
    skeleton produces a well-formed OutputDirective without touching the network.
    """

    def render(self, decision: ActionDecision, *, mode: str | None) -> str:
        kind = decision.content_kind or "utterance"
        speak_mode = mode or "companion"
        return f"[stub:{speak_mode}] Regis would speak a {kind} here ({decision.rationale})."


class ComposerRenderer:
    """Real renderer wrapping wisp.composer.compose_utterance (calls the LLM).

    Imported lazily so tests never pull in the LLM/composer module chain. Not
    used in any test-exercised code path; wired in a later fill.
    """

    def __init__(self, *, reasoning_effort: str = "low", verbosity: str = "low") -> None:
        self._reasoning_effort = reasoning_effort
        self._verbosity = verbosity

    def render(self, decision: ActionDecision, *, mode: str | None) -> str:
        from wisp.composer import compose_utterance  # lazy: keeps LLM out of import graph

        moment_kind = decision.content_kind or "conversation_tease"
        composed = compose_utterance(
            user_id=decision.user_id,
            moment_kind=moment_kind,
            explicit_context=decision.rationale,
            reasoning_effort=self._reasoning_effort,
            verbosity=self._verbosity,
        )
        return composed.text
