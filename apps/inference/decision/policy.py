# apps/inference/decision/policy.py
"""L5 policy contract: the shared shape every decision policy implements.

A policy is a pure function from DecisionContext -> ActionDecision. The
autonomous "should Regis speak?" choice is trust-critical, so the protocol
default action is "hold" (silence) and a policy must affirmatively clear its
safety gates to return "interject" (commitment #5 mode, #13 outcome-driven).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Protocol

from core.protocol.enums import MetaContext
from core.protocol.payloads import ActionDecision, Prediction


@dataclass
class DecisionContext:
    """Everything a policy needs to decide, lifted off the inbound envelope."""

    user_id: str
    prediction: Prediction
    meta_context: MetaContext
    consent_scope: str
    now: datetime                     # tz-aware UTC, the decision instant
    i_model_id: str | None = None

    def __post_init__(self) -> None:
        if self.now.tzinfo is None:
            raise ValueError("DecisionContext.now must be tz-aware UTC")


@dataclass
class GateResult:
    """One safety gate's verdict: passed (clear to speak) or blocked (HOLD)."""

    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


# A gate is a pure predicate over the context; returns its own GateResult.
Gate = Callable[[DecisionContext], GateResult]


class Policy(Protocol):
    """A named decision policy. Returns an ActionDecision (default action='hold')."""

    name: str

    def decide(self, ctx: DecisionContext) -> ActionDecision: ...


def run_gates(gates: list[Gate], ctx: DecisionContext) -> list[GateResult]:
    """Evaluate every gate (no short-circuit) so the trace records all of them."""
    return [gate(ctx) for gate in gates]


def gate_trace_dict(results: list[GateResult], *, policy: str) -> dict[str, Any]:
    """Pack gate verdicts into the ActionDecision.gate_trace payload."""
    return {
        "policy": policy,
        "all_passed": all(r.passed for r in results),
        "gates": [r.to_dict() for r in results],
    }
