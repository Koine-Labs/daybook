"""Consumer API for live priors. Source/confidence/population always travel along.

`applies_to_user` is a pure population/applicability gate (CI-tested). `priors_for`
and `weak_supervision_for` read live priors and never hide the source (so the #5
leave-one-source-out fusion grader can rank by TRUST_ORDER). `materialize_prior`
is the cold-start (#4) path; it is the only consumer that writes the ledger, and it
does so solely through emit.record_weak_label.
"""
from __future__ import annotations

from typing import Callable, Mapping
from uuid import UUID

from .models import (
    Context,
    LiteraturePrior,
    PriorStatus,
    SubjectProfile,
    WeakLabel,
    Window,
)
from .rules import evaluate_rule

_LITERATURE_PRIOR_SOURCE = "literature_prior"


def applies_to_user(prior: LiteraturePrior, subject: SubjectProfile | None) -> bool:
    """Pure population/applicability gate (age range, excludes, meta_context).

    With no hard gates a prior applies to everyone (incl. unknown subject). When
    hard gates exist and the subject is unknown, the prior does NOT apply.
    """
    appl = prior.applicability or {}
    has_age_gate = "age_min" in appl or "age_max" in appl
    excludes = appl.get("excludes") or []
    want_meta = appl.get("meta_context")
    has_hard_gate = has_age_gate or bool(excludes) or want_meta is not None

    if not has_hard_gate:
        return True
    if subject is None:
        return False

    if has_age_gate:
        if subject.age is None:
            return False
        if "age_min" in appl and subject.age < appl["age_min"]:
            return False
        if "age_max" in appl and subject.age > appl["age_max"]:
            return False
    if excludes:
        meds = {m.lower() for m in subject.medications}
        if any(str(e).lower() in meds for e in excludes):
            return False
    if want_meta is not None and subject.meta_context != want_meta:
        return False
    return True


def priors_for(
    axis: str,
    *,
    context: Context | None = None,
    subject: SubjectProfile | None = None,
    status: PriorStatus = PriorStatus.LIVE,
    lister: Callable | None = None,
) -> list[LiteraturePrior]:
    """Priors for an axis (default LIVE), population-filtered by applies_to_user."""
    if lister is None:
        from .store import list_priors as lister  # type: ignore[assignment]
    candidates = lister(axis=axis, status=status)
    return [p for p in candidates if applies_to_user(p, subject)]


def weak_supervision_for(
    axis: str,
    features: Mapping[str, float],
    context: Context,
    subject: SubjectProfile,
    *,
    lister: Callable | None = None,
) -> list[WeakLabel]:
    """Satisfied live priors -> down-weighted, source-tagged WeakLabels (#5/§6)."""
    out: list[WeakLabel] = []
    for prior in priors_for(axis, context=context, subject=subject, lister=lister):
        claim = evaluate_rule(prior.rule, features, context)
        if claim is None:
            continue
        out.append(
            WeakLabel(
                axis=claim.axis,
                claim=claim,
                confidence=prior.confidence,
                source=_LITERATURE_PRIOR_SOURCE,
                population=prior.population,
                citation=prior.citation,
                known_limitations=prior.known_limitations,
                literature_prior_id=prior.id,
            )
        )
    return out


def materialize_prior(
    prior_id: UUID,
    user_id: UUID,
    window: Window,
    features: Mapping[str, float],
    context: Context,
    *,
    loader: Callable | None = None,
    emitter: Callable | None = None,
) -> str | None:
    """COLD-START (#4): if the live prior fires on this window, write ONE ledger label.

    Returns the ledger id, or None if the prior is not live / doesn't fire / DB absent.
    """
    if loader is None:
        from .store import get_prior as loader  # type: ignore[assignment]
    prior = loader(prior_id)
    if prior is None or prior.status is not PriorStatus.LIVE:
        return None
    claim = evaluate_rule(prior.rule, features, context)
    if claim is None:
        return None
    if emitter is None:
        from .emit import record_weak_label as emitter  # type: ignore[assignment]
    return emitter(claim, prior, user_id, window, context)
