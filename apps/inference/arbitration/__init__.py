"""Cold-start arbitration (commitment #4): per-axis population<->personal mixing weight.

Consumes the FROZEN label ledger (labels/: LabelSource, LabelRecord, read_labels,
group_by_source) read-only. Pure math lives in blend/evidence/demographics/constants;
DB I/O is isolated in arbiter (recompute_axis) and read (get_calibration), both
crash-safe (mirror fusion/writer.py + loader.py).

LabelSource reconciliation (flagged): the spec's prose names SENSOR_INFERRED and
POPULATION_PRIOR tiers that are NOT in the frozen 8-value LabelSource enum. They are
mapped onto the real enum in constants.py:
  personal evidence = {SELF_REPORT, OBSERVED_OUTCOME, HEURISTIC}
  population pole    = {LITERATURE_PRIOR, DEMOGRAPHIC_PRIOR, LLM_LITERATURE_BOOTSTRAP}
"""
from __future__ import annotations

from typing import Any

from .blend import BlendResult, CalibrationState, blend, calibration_state_for
from .constants import ProfileParams, default_profile
from .demographics import ConsentedCohort, DemographicModifier, apply
from .evidence import TierEvidence, summarize

__all__ = [
    "blend",
    "calibration_state_for",
    "summarize",
    "apply",
    "recompute_axis",
    "get_calibration",
    "BlendResult",
    "CalibrationState",
    "TierEvidence",
    "ProfileParams",
    "default_profile",
    "ConsentedCohort",
    "DemographicModifier",
]


def __getattr__(name: str) -> Any:
    """Lazily expose the DB-touching seams so importing the package stays DB-free."""
    if name == "recompute_axis":
        from .arbiter import recompute_axis

        return recompute_axis
    if name == "get_calibration":
        from .read import get_calibration

        return get_calibration
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
