"""Truth-grader selection by the frozen TRUST_ORDER (A2) + proxy-grader stub.

Maps the truth tiers present in a set of GradedPairs onto the grader name recorded
in `ablation_results.grader`. ground_truth/clinician → ground_truth grader;
self_report → self_report grader; observed_outcome (or nothing) → proxy grader.
The proxy grader is a LABELED STUB (raises NotImplementedError) — never a silently
faked error signal (honesty value, open question O2).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from labels import TRUST_ORDER, LabelSource  # noqa: E402

from .dataset import GradedPair

GROUND_TRUTH_GRADER = "ground_truth"
SELF_REPORT_GRADER = "self_report"
PROXY_GRADER = "observed_outcome_proxy"

# Which grader name each truth tier resolves to.
_TIER_TO_GRADER: dict[LabelSource, str] = {
    LabelSource.GROUND_TRUTH: GROUND_TRUTH_GRADER,
    LabelSource.CLINICIAN: GROUND_TRUTH_GRADER,
    LabelSource.SELF_REPORT: SELF_REPORT_GRADER,
    LabelSource.OBSERVED_OUTCOME: PROXY_GRADER,
}


def select_truth_grader(pairs: Sequence[GradedPair]) -> str:
    """Pick the grader for the highest-trust tier present, ranked by TRUST_ORDER."""
    present = {p.truth_source for p in pairs}
    for tier in TRUST_ORDER:
        if tier in present and tier in _TIER_TO_GRADER:
            return _TIER_TO_GRADER[tier]
    return PROXY_GRADER


def proxy_outcome_error(
    pairs: Sequence[GradedPair], predictions: Sequence[float]
) -> list[float]:
    """Map observed_outcome ledger rows to an axis-error signal.

    DOCUMENTED STUB (open question O2): the contract is fixed — return one error
    per (pair, prediction) — but the v1 harness does not yet derive a calibrated
    outcome→axis-error mapping, so this raises rather than fabricate a signal.
    """
    raise NotImplementedError(
        "proxy_outcome_error is a labeled stub (O2): observed_outcome → axis-error "
        "mapping is not yet calibrated. Use self_report/ground_truth graders for v1."
    )
