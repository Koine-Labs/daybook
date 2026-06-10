"""Default tuning for cold-start arbitration (#4): tier trust, half-lives, E_* thresholds.

These mirror migration 0013's DEFAULTs. A cold_start_profiles row may override any
of them per (user, axis); absence falls back to these module constants.

LabelSource reconciliation (see package docstring): the spec's prose names
SENSOR_INFERRED / POPULATION_PRIOR tiers that do NOT exist in the frozen 8-value
LabelSource enum. They are mapped onto the real enum here:
  personal evidence = {SELF_REPORT, OBSERVED_OUTCOME, HEURISTIC}
  population pole    = {LITERATURE_PRIOR, DEMOGRAPHIC_PRIOR, LLM_LITERATURE_BOOTSTRAP}
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from labels import LabelSource

# Personal-evidence tiers (mapped onto the real frozen enum). HEURISTIC stands in
# for the spec's "sensor_inferred": L3 fusion scaffolds + device tags land at
# HEURISTIC via classify_source until a stronger source confirms them.
PERSONAL_TIERS: frozenset[LabelSource] = frozenset(
    {LabelSource.SELF_REPORT, LabelSource.OBSERVED_OUTCOME, LabelSource.HEURISTIC}
)

# Population-pole tiers — excluded from e_personal (they ARE the population side).
POPULATION_TIERS: frozenset[LabelSource] = frozenset(
    {
        LabelSource.LITERATURE_PRIOR,
        LabelSource.DEMOGRAPHIC_PRIOR,
        LabelSource.LLM_LITERATURE_BOOTSTRAP,
    }
)

# Per-tier trust multipliers (self_report > observed_outcome > heuristic/sensor).
DEFAULT_TIER_TRUST: dict[str, float] = {
    LabelSource.SELF_REPORT.value: 1.0,
    LabelSource.OBSERVED_OUTCOME.value: 0.7,
    LabelSource.HEURISTIC.value: 0.35,
}

# Per-tier exponential half-life in seconds (recency decay).
DEFAULT_TIER_HALFLIFE_S: dict[str, float] = {
    LabelSource.SELF_REPORT.value: 2_592_000.0,      # 30d
    LabelSource.OBSERVED_OUTCOME.value: 1_209_600.0,  # 14d
    LabelSource.HEURISTIC.value: 604_800.0,           # 7d
}

# Per-tier saturation cap on a SINGLE tier's summed (decayed*confidence) mass,
# BEFORE the tier-trust multiplier. This is the anti-swamp bound: high-volume
# low-trust streams saturate, so raw volume cannot beat a high-trust source.
DEFAULT_TIER_SATURATION: dict[str, float] = {
    LabelSource.SELF_REPORT.value: 1e9,    # effectively uncapped; self-report is ground-truth-grade
    LabelSource.OBSERVED_OUTCOME.value: 50.0,
    LabelSource.HEURISTIC.value: 2.0,      # sensor volume saturates fast: trust*cap=0.7 < one self_report (1.0)
}

# Default trust/half-life/saturation for any tier not explicitly listed above.
FALLBACK_TIER_TRUST: float = 0.2
FALLBACK_TIER_HALFLIFE_S: float = 604_800.0
FALLBACK_TIER_SATURATION: float = 1.0

# E_* thresholds (effective evidence mass).
DEFAULT_E_HALF: float = 8.0
DEFAULT_E_CS_ENTER: float = 0.5
DEFAULT_E_CS_EXIT: float = 0.25
DEFAULT_E_CAL_ENTER: float = 6.0
DEFAULT_E_CAL_EXIT: float = 4.0

# Population-pole literature defaults when no cold_start_profiles row exists.
FALLBACK_POPULATION_VALUE: float = 0.0
FALLBACK_POPULATION_VARIANCE: float = 1.0

# The current live L3 affect axes (seeded by migration 0013 / #3).
LIVE_AXES: tuple[str, ...] = (
    "arousal",
    "valence",
    "arousal_inferred",
    "affect_prosody",
    "sleep_stage",
    "state_declared",
    "engagement",
)


@dataclass(frozen=True)
class ProfileParams:
    """Per-axis tuning, sourced from a cold_start_profiles row or these defaults."""

    axis: str
    population_value: float = FALLBACK_POPULATION_VALUE
    population_variance: float = FALLBACK_POPULATION_VARIANCE
    literature_source: str | None = None
    e_half: float = DEFAULT_E_HALF
    e_cs_enter: float = DEFAULT_E_CS_ENTER
    e_cs_exit: float = DEFAULT_E_CS_EXIT
    e_cal_enter: float = DEFAULT_E_CAL_ENTER
    e_cal_exit: float = DEFAULT_E_CAL_EXIT
    tier_trust: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TIER_TRUST))
    tier_halflife_s: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TIER_HALFLIFE_S))
    tier_saturation: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TIER_SATURATION))

    def trust_for(self, tier: str) -> float:
        return self.tier_trust.get(tier, FALLBACK_TIER_TRUST)

    def halflife_for(self, tier: str) -> float:
        return self.tier_halflife_s.get(tier, FALLBACK_TIER_HALFLIFE_S)

    def saturation_for(self, tier: str) -> float:
        return self.tier_saturation.get(tier, FALLBACK_TIER_SATURATION)


def default_profile(axis: str) -> ProfileParams:
    """A ProfileParams carrying module-default tuning for an axis (no DB)."""
    return ProfileParams(axis=axis)
