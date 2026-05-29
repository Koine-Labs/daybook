# apps/inference/core/protocol/payloads.py
"""Per-layer message payloads.

L2 (FeatureSnapshot) and L3 (BeliefState/AxisEstimate) payloads are reused from
their owning modules and re-exported here so the protocol has one import home.
The four payloads that don't exist elsewhere are defined here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

from features.snapshot import FeatureSnapshot
from fusion.belief_state import AxisEstimate, BeliefState

# L2 payload is the FeatureSnapshot itself; alias keeps the protocol name explicit.
FeaturePacket = FeatureSnapshot

__all__ = [
    "SignalPacket", "FeaturePacket", "FeatureSnapshot", "BeliefState", "AxisEstimate",
    "Prediction", "ActionDecision", "OutputDirective",
]


def _require_utc(name: str, ts: datetime) -> None:
    if ts.tzinfo is None:
        raise ValueError(f"{name} must be tz-aware UTC")


@dataclass
class SignalPacket:
    """L1 -> L2. Intent- and modality-tagged signal (commitment #10).

    Semantic-first (#11): only meaningful extractions ride here, never raw bytes.
    """

    user_id: str
    timestamp: datetime               # tz-aware UTC
    modality: str                     # a Modality value
    intent: str                       # an Intent value
    kind: str                         # e.g. 'speech_final', 'hr_30s', 'mac_activity'
    payload: dict[str, Any]
    source: str                       # e.g. 'mac.mic', 'watch.hr_30s'
    confidence: float | None = None
    i_model_id: str | None = None     # commitment #1

    def __post_init__(self) -> None:
        _require_utc("SignalPacket.timestamp", self.timestamp)
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class Prediction:
    """L4 -> L5. Forecast for (axis, horizon, action), with provenance (#15/#16)."""

    user_id: str
    axis: str
    made_at: datetime                 # tz-aware UTC
    horizon_seconds: int
    distribution: dict[str, Any]      # categorical probs or {mean, variance}
    model_id: str
    confidence: float | None = None
    action: dict[str, Any] | None = None  # None = baseline; non-null = counterfactual
    provenance: Literal["placeholder", "calibrated"] = "placeholder"
    cold_start: bool = False
    i_model_id: str | None = None

    def __post_init__(self) -> None:
        _require_utc("Prediction.made_at", self.made_at)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["made_at"] = self.made_at.isoformat()
        return d


@dataclass
class ActionDecision:
    """L5 -> L6. Chosen action + rationale + safety-gate trace."""

    user_id: str
    decided_at: datetime              # tz-aware UTC
    action: Literal["interject", "hold"]
    rationale: str
    mode: Literal["witness", "companion"] | None = None
    content_kind: str | None = None
    gate_trace: dict[str, Any] = field(default_factory=dict)
    i_model_id: str | None = None

    def __post_init__(self) -> None:
        _require_utc("ActionDecision.decided_at", self.decided_at)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["decided_at"] = self.decided_at.isoformat()
        return d


@dataclass
class OutputDirective:
    """L6 -> channel. Rendered intent + channel + delivery params (voice primary, #3)."""

    user_id: str
    created_at: datetime              # tz-aware UTC
    channel: Literal["voice", "haptic", "visual"]
    mode: Literal["witness", "companion"] | None = None
    text: str | None = None
    delivery: dict[str, Any] = field(default_factory=dict)
    i_model_id: str | None = None

    def __post_init__(self) -> None:
        _require_utc("OutputDirective.created_at", self.created_at)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d
