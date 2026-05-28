"""BeliefState + per-axis estimates with freshness policy.

Per ARCHITECTURE.md §3 L3: BeliefState holds the current best per-axis
estimates, each with a freshness window. Reads enforce freshness — stale
axes return None instead of letting callers act on outdated data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

DEFAULT_FRESH_SECONDS = 120


@dataclass
class AxisEstimate:
    """One per-axis state estimate produced by L3 fusion."""

    axis: str
    value: dict[str, Any]              # e.g., {"category": "waking/focused"} or {"label": "rem", "prob": 0.71}
    timestamp: datetime                # tz-aware UTC, when this estimate was *produced*
    confidence: float | None
    source: str                        # e.g., 'L3.fusion.meta_context', 'apple_health_sleep_stage'
    meta_context: str | None = None    # optional sub-tag if known
    i_model_id: str | None = None
    fresh_for_seconds: int = DEFAULT_FRESH_SECONDS

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("AxisEstimate.timestamp must be tz-aware UTC")

    def is_fresh(self, *, now: datetime | None = None) -> bool:
        if now is None:
            now = datetime.now(timezone.utc)
        return (now - self.timestamp).total_seconds() <= self.fresh_for_seconds


@dataclass
class BeliefState:
    """Per-user bundle of current per-axis estimates with freshness gates."""

    user_id: str
    estimates: dict[str, AxisEstimate] = field(default_factory=dict)

    def update(self, est: AxisEstimate) -> None:
        """Replace the current estimate for the given axis."""
        self.estimates[est.axis] = est

    def get(self, axis: str, *, now: datetime | None = None) -> AxisEstimate | None:
        """Return the axis estimate iff it's fresh; else None."""
        est = self.estimates.get(axis)
        if est is None:
            return None
        return est if est.is_fresh(now=now) else None

    def snapshot(self, *, now: datetime | None = None) -> dict[str, dict[str, Any]]:
        """Dict of {axis: value_dict} for fresh axes only — for prompt assembly."""
        out: dict[str, dict[str, Any]] = {}
        for axis, est in self.estimates.items():
            if est.is_fresh(now=now):
                out[axis] = {
                    "value": est.value,
                    "confidence": est.confidence,
                    "source": est.source,
                    "timestamp": est.timestamp.isoformat(),
                }
        return out
