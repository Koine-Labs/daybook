"""Typed models for the literature-prior registry — #17 invariants enforced here.

Pure: no DB, no LLM, no network at module scope. The dataclasses validate the
commitment-#17 demands in `__post_init__` (rule.claim.axis == target_axis,
confidence in [0,1], non-empty known_limitations) so an invalid prior can never
reach the registry or the ledger.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

OPERATORS: frozenset[str] = frozenset(
    {"decrease", "increase", "gt", "lt", "in_band", "ratio_gt"}
)
DIRECTIONS: frozenset[str] = frozenset({"increase", "decrease"})


class PriorStatus(str, Enum):
    """Lifecycle of a registry prior. Only LIVE is consumable/materializable."""

    CANDIDATE = "candidate"
    REVIEWED = "reviewed"
    LIVE = "live"
    RETIRED = "retired"


class PriorOrigin(str, Enum):
    """How a prior entered the registry."""

    LLM_LITERATURE_BOOTSTRAP = "llm_literature_bootstrap"
    HAND_ENTERED = "hand_entered"
    SEED = "seed"


@dataclass
class RuleClaim:
    """What a rule asserts about an axis when its condition fires."""

    axis: str
    direction: str | None = None
    value: Any = None
    magnitude: str = "weak"

    def __post_init__(self) -> None:
        if not self.axis:
            raise ValueError("RuleClaim.axis must be non-empty")
        if self.direction is not None and self.direction not in DIRECTIONS:
            raise ValueError(f"RuleClaim.direction must be one of {sorted(DIRECTIONS)}")
        if self.direction is None and self.value is None:
            raise ValueError("RuleClaim must carry a direction or a value")

    def to_dict(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "direction": self.direction,
            "value": self.value,
            "magnitude": self.magnitude,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RuleClaim:
        return cls(
            axis=d["axis"],
            direction=d.get("direction"),
            value=d.get("value"),
            magnitude=d.get("magnitude", "weak"),
        )


@dataclass
class Rule:
    """A feature-condition -> claimed-value rule (canonical `rule` JSONB schema)."""

    feature: str
    operator: str
    claim: RuleClaim
    modality: str = "biometric"
    threshold: float | None = None
    window_s: int = 60
    context_gate: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.feature:
            raise ValueError("Rule.feature must be non-empty")
        if self.operator not in OPERATORS:
            raise ValueError(f"Rule.operator must be one of {sorted(OPERATORS)}")
        if self.operator in {"gt", "lt", "ratio_gt"} and self.threshold is None:
            raise ValueError(f"Rule.operator {self.operator!r} requires a threshold")
        if self.operator == "in_band":
            if not (isinstance(self.threshold, (list, tuple)) and len(self.threshold) == 2):
                raise ValueError("Rule.operator 'in_band' requires a [lo, hi] threshold")

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "modality": self.modality,
            "operator": self.operator,
            "threshold": list(self.threshold)
            if isinstance(self.threshold, (list, tuple))
            else self.threshold,
            "window_s": self.window_s,
            "claim": self.claim.to_dict(),
            "context_gate": dict(self.context_gate),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Rule:
        thr = d.get("threshold")
        if isinstance(thr, list):
            thr = tuple(thr)
        return cls(
            feature=d["feature"],
            operator=d["operator"],
            claim=RuleClaim.from_dict(d["claim"]),
            modality=d.get("modality", "biometric"),
            threshold=thr,
            window_s=d.get("window_s", 60),
            context_gate=d.get("context_gate", {}) or {},
        )


@dataclass
class LiteratureSource:
    """A curated source document (paper / dataset / textbook / review)."""

    citation: str
    source_kind: str
    doi: str | None = None
    url: str | None = None
    corpus_path: str | None = None
    population_note: str | None = None
    added_by: str = "human"
    id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.citation:
            raise ValueError("LiteratureSource.citation must be non-empty")
        if not self.source_kind:
            raise ValueError("LiteratureSource.source_kind must be non-empty")


@dataclass
class LiteraturePrior:
    """One weak, citation-backed prior — a reusable, population-level rule (#17).

    NOT a ledger label: carries no user_id. Becomes a ledger row only at
    materialization. The #17-required fields (target_axis, rule, citation via
    source_id, population, confidence, known_limitations) are all mandatory.
    """

    target_axis: str
    rule: Rule
    claim_summary: str
    population: str
    confidence: float
    known_limitations: str
    source_id: UUID
    origin: PriorOrigin
    applicability: dict[str, Any] = field(default_factory=dict)
    extracted_excerpt: str | None = None
    status: PriorStatus = PriorStatus.CANDIDATE
    superseded_by: UUID | None = None
    id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    citation: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.origin, PriorOrigin):
            self.origin = PriorOrigin(self.origin)
        if not isinstance(self.status, PriorStatus):
            self.status = PriorStatus(self.status)
        if not self.target_axis:
            raise ValueError("LiteraturePrior.target_axis must be non-empty")
        if self.rule.claim.axis != self.target_axis:
            raise ValueError(
                "LiteraturePrior.rule.claim.axis must equal target_axis "
                f"({self.rule.claim.axis!r} != {self.target_axis!r})"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("LiteraturePrior.confidence must be in [0, 1]")
        if not self.known_limitations or not self.known_limitations.strip():
            raise ValueError("LiteraturePrior.known_limitations must be non-empty (#17)")
        if not self.claim_summary or not self.claim_summary.strip():
            raise ValueError("LiteraturePrior.claim_summary must be non-empty")
        if not self.population or not self.population.strip():
            raise ValueError("LiteraturePrior.population must be non-empty")


@dataclass
class Promotion:
    """The result/audit of a promotion-gate decision."""

    prior_id: UUID
    from_status: PriorStatus
    to_status: PriorStatus
    evidence_axis: str
    evidence_label_count: int
    evidence_sources: list[str]
    validation_metric: str
    passed: bool
    decided_by: str
    evidence_user_id: UUID | None = None
    validation_score: float | None = None
    rationale: str | None = None
    id: UUID | None = None


@dataclass(frozen=True)
class Context:
    """Runtime evaluation context (commitment #14 meta/sub-context bias)."""

    meta_context: str | None = None
    sub_context: str | None = None


@dataclass(frozen=True)
class SubjectProfile:
    """Population attributes of the concrete user a prior may be applied to."""

    age: int | None = None
    medications: tuple[str, ...] = ()
    meta_context: str | None = None


@dataclass(frozen=True)
class Window:
    """A concrete analysis window over which a prior is materialized."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Window.start/end must be tz-aware UTC")


@dataclass
class WeakLabel:
    """A down-weighted, source-tagged weak-supervision signal (never hides source)."""

    axis: str
    claim: RuleClaim
    confidence: float
    source: str
    population: str
    citation: str | None
    known_limitations: str
    literature_prior_id: UUID | None = None
