"""Pure, bias-safe opt-in demographic modifiers on the POPULATION pole only.

No DB, no LLM. Demographics are opt-in uncertainty modifiers, auditable, and never
hard-classifying: value_shift is capped to +/-max_abs_shift; variance_scale<1 is
rejected (demographics may add doubt, never certainty); nothing applies without a
consented cohort match on an enabled modifier. The effect is on the population
prior only — it never touches w_personal or any personal-tier evidence.

Caller (arbiter) passes ONLY this axis's enabled modifier rows and ONLY the user's
consented cohort rows; apply() matches them on (cohort_key, cohort_value).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ConsentedCohort:
    """A cohort the user has explicitly consented to use (from user_demographics)."""

    cohort_key: str
    cohort_value: str


@dataclass(frozen=True)
class DemographicModifier:
    """An enabled demographic_priors row — a capped, provenance-marked modifier."""

    axis: str
    cohort_key: str
    cohort_value: str
    value_shift: float
    variance_scale: float
    max_abs_shift: float
    source: str
    enabled: bool = False
    bias_notes: str | None = None


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def apply(
    population_value: float,
    population_variance: float,
    cohorts: Sequence[ConsentedCohort],
    modifiers: Sequence[DemographicModifier],
) -> tuple[float, float, bool]:
    """Return (modified_value, modified_variance, applied_flag) — bias-safe.

    Rules (locked): only enabled modifiers whose (cohort_key, cohort_value) match a
    consented cohort apply; value_shift is clamped to +/-max_abs_shift; variance_scale
    must be >= 1 (narrowing rejected). applied is False (inputs unchanged) when no
    modifier had an effective shift or widening.
    """
    consented = {(c.cohort_key, c.cohort_value) for c in cohorts}
    value = population_value
    variance = population_variance
    applied = False
    for mod in modifiers:
        if not mod.enabled:
            continue
        if (mod.cohort_key, mod.cohort_value) not in consented:
            continue
        shift = _clamp(mod.value_shift, -abs(mod.max_abs_shift), abs(mod.max_abs_shift))
        if shift != 0.0:
            value += shift
            applied = True
        # variance_scale < 1 would NARROW (add certainty) -> reject silently.
        if mod.variance_scale >= 1.0 and mod.variance_scale != 1.0:
            variance *= mod.variance_scale
            applied = True
    return value, variance, applied
