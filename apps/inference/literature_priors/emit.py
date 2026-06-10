"""The ONLY chokepoint that writes weak labels into the #1 ledger.

`record_weak_label` builds a LabelRecord at source=LITERATURE_PRIOR with full
#17 provenance round-tripped (literature_prior_id, citation, population,
known_limitations, proposed_source, idempotency_key) and calls
labels.ledger.record_label. Crash-safe: returns None when the DB is absent
(mirrors ledger.record_label). The labels import lives inside the function so
pytest collection stays DB-free / LLM-free.
"""
from __future__ import annotations

import hashlib
from typing import Callable
from uuid import UUID

from .models import Context, LiteraturePrior, RuleClaim, Window


def _idempotency_key(prior_id: UUID, user_id: UUID, window: Window) -> str:
    raw = f"{prior_id}|{user_id}|{window.start.isoformat()}|{window.end.isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _encode_value(claim: RuleClaim) -> object:
    """Encode the claim onto the ledger `value` (#2/live-axis convention)."""
    if claim.value is not None:
        return claim.value
    return {"direction": claim.direction, "magnitude": claim.magnitude}


def record_weak_label(
    claim: RuleClaim,
    prior: LiteraturePrior,
    user_id: UUID,
    window: Window,
    context: Context | None = None,
    *,
    recorder: Callable | None = None,
) -> str | None:
    """Write ONE weak label at source=LITERATURE_PRIOR. Returns the ledger id or None.

    `recorder` is an injection seam for tests (defaults to labels.ledger.record_label).
    """
    from labels import LabelRecord, LabelSource  # local import: DB-free collection
    from labels.ledger import record_label

    provenance = {
        "literature_prior_id": str(prior.id) if prior.id is not None else None,
        "citation": prior.citation,
        "population": prior.population,
        "known_limitations": prior.known_limitations,
        "proposed_source": prior.origin.value,
        "idempotency_key": _idempotency_key(
            prior.id if prior.id is not None else UUID(int=0), user_id, window
        ),
    }
    record = LabelRecord(
        user_id=str(user_id),
        axis=claim.axis,
        value=_encode_value(claim),
        source=LabelSource.LITERATURE_PRIOR,
        observed_at=window.end,
        confidence=prior.confidence,
        provenance=provenance,
        consent_scope="literature_prior_v1",
        meta_context=context.meta_context if context is not None else None,
    )
    write = recorder if recorder is not None else record_label
    return write(record)
