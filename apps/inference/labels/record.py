"""LabelRecord — one provenance-bearing label row (mirrors label_observations)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .provenance import LabelSource


@dataclass
class LabelRecord:
    """One calibration-grade label keyed to an axis, with recorded provenance."""

    user_id: str
    axis: str
    value: Any                                    # scalar / category / distribution claimed
    source: LabelSource
    observed_at: datetime                         # tz-aware UTC, when the labeled moment occurred
    confidence: float = 0.5
    provenance: dict[str, Any] = field(default_factory=dict)
    consent_scope: str = "unscoped_v0"
    i_model_id: str | None = None
    meta_context: str | None = None

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("LabelRecord.observed_at must be tz-aware UTC")
        if not isinstance(self.source, LabelSource):
            self.source = LabelSource(self.source)

    def to_row(self) -> tuple[Any, ...]:
        """Positional tuple for the INSERT in ledger.record_label."""
        return (
            self.user_id,
            self.axis,
            self.value,
            self.confidence,
            self.source.value,
            self.provenance,
            self.consent_scope,
            self.i_model_id,
            self.meta_context,
            self.observed_at,
        )
