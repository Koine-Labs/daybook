"""Literature-Prior Registry — curated, citation-backed weak priors (commitment #17).

Priors are population-level rules (feature condition -> claimed axis value) carrying
citation, population, confidence, and known_limitations. They are NOT ledger labels:
a `literature_priors` row becomes a `label_observations` row only when a *live* prior
is materialized over a concrete (user, window) via `materialize_prior`. This package
consumes the frozen `labels/` ledger as-is; it never forks or alters it.
"""
from __future__ import annotations

from .consume import (
    applies_to_user,
    materialize_prior,
    priors_for,
    weak_supervision_for,
)
from .gate import promote_prior, validate_against_ledger
from .models import (
    Context,
    LiteraturePrior,
    LiteratureSource,
    PriorOrigin,
    PriorStatus,
    Promotion,
    Rule,
    RuleClaim,
    SubjectProfile,
    WeakLabel,
    Window,
)
from .store import register_candidate, retire_prior, review_prior

__all__ = [
    "Context",
    "LiteraturePrior",
    "LiteratureSource",
    "PriorOrigin",
    "PriorStatus",
    "Promotion",
    "Rule",
    "RuleClaim",
    "SubjectProfile",
    "WeakLabel",
    "Window",
    "register_candidate",
    "review_prior",
    "promote_prior",
    "validate_against_ledger",
    "retire_prior",
    "priors_for",
    "weak_supervision_for",
    "materialize_prior",
    "applies_to_user",
]
