"""Promotion gate: validate a candidate against ledger evidence, then promote.

The gate READS the #1 ledger (GROUND_TRUTH/SELF_REPORT/OBSERVED_OUTCOME), scores
the rule's predicted direction against observed evidence, and only flips a prior
to `live` when evidence_count >= min_labels AND score >= threshold AND a human
reviewer signed off. It writes a literature_prior_promotions audit row (pass or
fail) but NEVER writes the ledger. The ledger reader and store writers are
injectable so the scoring math is CI-tested with no DB.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable, Sequence
from uuid import UUID

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from .models import LiteraturePrior, PriorStatus, Promotion, Rule
from .rules import evaluate_rule

logger = logging.getLogger(__name__)

_DEFAULT_EVIDENCE_SOURCES = ("ground_truth", "self_report", "observed_outcome")


def _observed_direction(value: object) -> str | None:
    """Extract a directional sign from a ledger label value, or None."""
    if isinstance(value, dict):
        if value.get("direction") in ("increase", "decrease"):
            return value["direction"]
        for key in ("delta", "change", "value"):
            v = value.get(key)
            if isinstance(v, (int, float)):
                return "increase" if v > 0 else ("decrease" if v < 0 else None)
        return None
    if isinstance(value, (int, float)):
        return "increase" if value > 0 else ("decrease" if value < 0 else None)
    return None


def sign_agreement_rate(rule: Rule, evidence: Sequence) -> tuple[float | None, int]:
    """Fraction of evidence labels whose observed direction matches the rule's claim.

    Returns (score, comparable_count). Only labels with co-located feature data
    (`provenance.features`) and a recoverable observed direction are comparable.
    """
    matches = 0
    comparable = 0
    claim_dir = rule.claim.direction
    for label in evidence:
        prov = getattr(label, "provenance", None) or {}
        features = prov.get("features")
        if not isinstance(features, dict):
            continue
        predicted = evaluate_rule(rule, features)
        if predicted is None:
            continue
        observed = _observed_direction(getattr(label, "value", None))
        if observed is None:
            continue
        comparable += 1
        if claim_dir is not None and predicted.direction == observed:
            matches += 1
    if comparable == 0:
        return None, 0
    return matches / comparable, comparable


def validate_against_ledger(
    prior: LiteraturePrior,
    evidence_user_id: UUID,
    *,
    metric: str = "sign_agreement_rate",
    min_labels: int = 20,
    threshold: float = 0.6,
    reader: Callable | None = None,
) -> Promotion:
    """Score the prior's rule against ledger evidence; build a (not-yet-persisted) Promotion.

    `reader` defaults to labels.ledger.read_labels (imported lazily so collection
    stays DB-free). `passed` is set per the §6 gate condition; status flip is the
    caller's (promote_prior) job.
    """
    if reader is None:
        from labels.ledger import read_labels  # local import: DB-free collection
        from labels import LabelSource

        sources = [
            LabelSource.GROUND_TRUTH,
            LabelSource.SELF_REPORT,
            LabelSource.OBSERVED_OUTCOME,
        ]
        evidence = read_labels(str(evidence_user_id), axis=prior.target_axis, sources=sources)
    else:
        evidence = reader(prior.target_axis, evidence_user_id)

    if metric != "sign_agreement_rate":
        raise ValueError(f"unsupported validation metric: {metric!r}")

    score, comparable = sign_agreement_rate(prior.rule, evidence)
    total = len(evidence)
    passed = (
        comparable >= min_labels
        and score is not None
        and score >= threshold
    )
    return Promotion(
        prior_id=prior.id if prior.id is not None else UUID(int=0),
        from_status=prior.status,
        to_status=PriorStatus.LIVE if passed else prior.status,
        evidence_user_id=evidence_user_id,
        evidence_axis=prior.target_axis,
        evidence_label_count=comparable,
        evidence_sources=list(_DEFAULT_EVIDENCE_SOURCES),
        validation_metric=metric,
        validation_score=score,
        passed=passed,
        decided_by="",
    )


def promote_prior(
    prior_id: UUID,
    *,
    reviewer: str,
    evidence_user_id: UUID,
    metric: str = "sign_agreement_rate",
    min_labels: int = 20,
    threshold: float = 0.6,
    reader: Callable | None = None,
    prior_loader: Callable | None = None,
    promotion_writer: Callable | None = None,
    status_setter: Callable | None = None,
) -> Promotion:
    """THE GATE. reviewed -> live iff validate_against_ledger passes AND reviewer given.

    Auto-promotion forbidden: reviewer must be non-empty. Writes a promotions audit
    row (pass or fail) and, on pass, flips status to live. All IO is injectable.
    """
    if not reviewer:
        raise ValueError("promote_prior requires a human reviewer (auto-promotion forbidden)")

    if prior_loader is None:
        from .store import get_prior as prior_loader  # type: ignore[assignment]
    prior = prior_loader(prior_id)
    if prior is None:
        raise ValueError(f"prior {prior_id} not found")

    promo = validate_against_ledger(
        prior,
        evidence_user_id,
        metric=metric,
        min_labels=min_labels,
        threshold=threshold,
        reader=reader,
    )
    promo.prior_id = prior_id
    promo.decided_by = reviewer

    if promotion_writer is None:
        from .store_promotions import write_promotion as promotion_writer  # type: ignore[assignment]
    promotion_writer(promo)

    if promo.passed:
        if status_setter is None:
            from .store import _set_status as status_setter  # type: ignore[assignment]
        status_setter(prior_id, PriorStatus.LIVE)
        promo.to_status = PriorStatus.LIVE
    else:
        promo.to_status = prior.status
        logger.info("promote_prior denied for %s (score=%s)", prior_id, promo.validation_score)
    return promo
