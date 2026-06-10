"""LabelSource taxonomy — the eight commitment-#17 provenance tiers."""
from __future__ import annotations

from enum import Enum


class LabelSource(str, Enum):
    """The eight #17 label sources, in no implied order (see TRUST_ORDER)."""

    GROUND_TRUTH = "ground_truth"
    SELF_REPORT = "self_report"
    OBSERVED_OUTCOME = "observed_outcome"
    HEURISTIC = "heuristic"
    LITERATURE_PRIOR = "literature_prior"
    DEMOGRAPHIC_PRIOR = "demographic_prior"
    LLM_LITERATURE_BOOTSTRAP = "llm_literature_bootstrap"
    CLINICIAN = "clinician"


# Epistemic ladder, most-trusted first. Used for source-set fusion (#17 §6).
TRUST_ORDER: tuple[LabelSource, ...] = (
    LabelSource.GROUND_TRUTH,
    LabelSource.CLINICIAN,
    LabelSource.SELF_REPORT,
    LabelSource.OBSERVED_OUTCOME,
    LabelSource.LITERATURE_PRIOR,
    LabelSource.DEMOGRAPHIC_PRIOR,
    LabelSource.LLM_LITERATURE_BOOTSTRAP,
    LabelSource.HEURISTIC,
)

# Substrings that lift a freetext axis `source` above the default HEURISTIC tier.
# arousal_inferred's HR/HRV map has literature grounding (#17 §6 / spec §6).
_LITERATURE_HINTS: tuple[str, ...] = (
    "arousal_inferred",
    "literature",
    "hrv",
)


def classify_source(source_str: str) -> LabelSource:
    """Normalize a freetext provenance string onto a LabelSource tier.

    Exact enum values map to themselves; otherwise descriptive axis `source`
    strings (e.g. 'L3.fusion.meta_context.v1_heuristic') resolve to a tier so the
    whole system speaks one provenance vocabulary (#17 / spec §6).
    """
    s = (source_str or "").strip().lower()
    for member in LabelSource:
        if s == member.value:
            return member
    if any(hint in s for hint in _LITERATURE_HINTS):
        return LabelSource.LITERATURE_PRIOR
    # All other live-axis sources (heuristic scaffolds, watch/cam/mic device tags)
    # are priors of the weakest tier until a stronger source confirms them.
    return LabelSource.HEURISTIC
