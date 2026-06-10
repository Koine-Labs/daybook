"""LLM-extraction workflow — human-reviewable candidate proposer (NOT autonomous).

Reads ONLY local curated excerpts under the package seed/ tree (a path-escape guard
raises otherwise), asks an injected ChatClient to extract candidate rules in the
canonical schema, and returns origin='llm_literature_bootstrap', status='candidate'
objects. dry_run=True (default) returns proposals WITHOUT persisting. This module
imports NO HTTP client and performs no network IO of its own (commitment #11:
triggered, batch, human-gated — never continuous, never on raw streams).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .models import LiteraturePrior, PriorOrigin, PriorStatus, Rule, RuleClaim

logger = logging.getLogger(__name__)

SEED_ROOT = Path(__file__).resolve().parent / "seed"


# LLM wire-schema for ChatClient.chat_structured (which takes a Pydantic class and
# returns a validated INSTANCE). Deliberately lenient — every field defaulted — so the
# structured call always validates; the SEMANTIC gate (_to_prior + the models'
# __post_init__ invariants) rejects incomplete/invalid priors, matching "be
# conservative, drop the malformed."
class _ExtractedClaim(BaseModel):
    axis: str | None = None
    direction: str | None = None
    value: Any = None
    magnitude: str = "weak"


class _ExtractedRule(BaseModel):
    feature: str = ""
    modality: str | None = None
    operator: str = ""
    threshold: Any = None
    window_s: int | None = None
    claim: _ExtractedClaim = Field(default_factory=_ExtractedClaim)
    context_gate: dict[str, Any] = Field(default_factory=dict)


class _ExtractedPrior(BaseModel):
    target_axis: str | None = None
    rule: _ExtractedRule = Field(default_factory=_ExtractedRule)
    claim_summary: str = ""
    population: str = ""
    confidence: float | None = None
    known_limitations: str = ""
    extracted_excerpt: str | None = None
    applicability: dict[str, Any] = Field(default_factory=dict)


class ExtractedPriorBatch(BaseModel):
    """The structured-output schema for one extraction call (a batch of candidates)."""

    priors: list[_ExtractedPrior] = Field(default_factory=list)


def _resolve_within_seed(corpus_dir: Path) -> Path:
    """Honesty guard: corpus_dir MUST resolve inside the package seed/ tree."""
    resolved = corpus_dir.resolve()
    root = SEED_ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(
            f"corpus_dir must be inside the package seed/ tree ({root}); got {resolved}"
        )
    return resolved


def _read_excerpts(corpus_dir: Path) -> list[tuple[str, str]]:
    excerpts: list[tuple[str, str]] = []
    for path in sorted(corpus_dir.glob("*.txt")):
        excerpts.append((path.name, path.read_text(encoding="utf-8")))
    return excerpts


def _build_prompt(excerpts: list[tuple[str, str]], axes: Sequence[str]) -> str:
    blocks = "\n\n".join(f"### {name}\n{text}" for name, text in excerpts)
    return (
        "Extract weak, citation-backed priors mapping a sensor/feature condition to a "
        "claimed value on one of these axes: " + ", ".join(axes) + ".\n"
        "Each prior MUST include honest known_limitations and a population. Use the "
        "canonical rule schema (feature, modality, operator in "
        "[decrease,increase,gt,lt,in_band,ratio_gt], threshold, window_s, claim{axis,"
        "direction,value,magnitude}, context_gate). claim.axis MUST equal target_axis.\n\n"
        "Source excerpts:\n" + blocks
    )


def _to_prior(raw: dict[str, Any], source_id: UUID) -> LiteraturePrior:
    rd = raw["rule"]
    rule = Rule(
        feature=rd["feature"],
        operator=rd["operator"],
        claim=RuleClaim.from_dict(rd["claim"]),
        modality=rd.get("modality", "biometric"),
        threshold=(tuple(rd["threshold"]) if isinstance(rd.get("threshold"), list) else rd.get("threshold")),
        window_s=rd.get("window_s", 60),
        context_gate=rd.get("context_gate", {}) or {},
    )
    return LiteraturePrior(
        target_axis=raw["target_axis"],
        rule=rule,
        claim_summary=raw["claim_summary"],
        population=raw["population"],
        confidence=float(raw["confidence"]),
        known_limitations=raw["known_limitations"],
        source_id=source_id,
        origin=PriorOrigin.LLM_LITERATURE_BOOTSTRAP,
        extracted_excerpt=raw.get("extracted_excerpt"),
        applicability=raw.get("applicability", {}) or {},
        status=PriorStatus.CANDIDATE,
    )


def propose_candidates_from_corpus(
    corpus_dir: Path,
    axes: Sequence[str],
    client: Any,
    dry_run: bool = True,
    *,
    source_id: UUID | None = None,
) -> list[LiteraturePrior]:
    """Propose llm_literature_bootstrap candidates from LOCAL curated excerpts only.

    dry_run=True (default) returns proposals WITHOUT persisting; a human reviews/edits
    then calls register_candidate on the keepers. `client` is any object exposing
    `chat_structured(system, user, schema) -> dict` (injected; stubbed in tests).
    """
    corpus_dir = _resolve_within_seed(Path(corpus_dir))
    excerpts = _read_excerpts(corpus_dir)
    if not excerpts:
        logger.warning("propose_candidates_from_corpus: no .txt excerpts in %s", corpus_dir)
        return []

    sid = source_id if source_id is not None else uuid4()
    prompt = _build_prompt(excerpts, axes)
    system = (
        "You extract weak physiological/behavioral priors from curated literature "
        "excerpts. Honesty over completeness: always include known_limitations."
    )
    result = client.chat_structured(system=system, user=prompt, schema=ExtractedPriorBatch)
    # Real client returns an ExtractedPriorBatch instance; tolerate a JSON string or
    # dict for resilience against alternate client shims.
    if isinstance(result, str):
        result = json.loads(result)
    if isinstance(result, BaseModel):
        raw_priors = [p.model_dump() for p in result.priors]
    elif isinstance(result, dict):
        raw_priors = result.get("priors", [])
    else:
        raw_priors = []

    proposals: list[LiteraturePrior] = []
    for raw in raw_priors:
        try:
            proposals.append(_to_prior(raw, sid))
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("skipping malformed candidate: %s", exc)

    if not dry_run:
        from .store import register_candidate  # local import: DB-free collection

        for prior in proposals:
            register_candidate(prior)
    return proposals
