"""DB-free + LLM-free bias-safety tests for demographics.apply()."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from arbitration.demographics import ConsentedCohort, DemographicModifier, apply


def _cohort(key="age_band", value="25-34"):
    return ConsentedCohort(cohort_key=key, cohort_value=value)


def _mod(**kw):
    base = dict(
        axis="arousal",
        cohort_key="age_band",
        cohort_value="25-34",
        value_shift=0.1,
        variance_scale=1.0,
        max_abs_shift=0.05,
        source="some_dataset_2024",
        enabled=True,
    )
    base.update(kw)
    return DemographicModifier(**base)


def test_no_consented_cohort_returns_unchanged_not_applied():
    v, var, applied = apply(0.3, 1.0, cohorts=[], modifiers=[_mod()])
    assert (v, var, applied) == (0.3, 1.0, False)


def test_disabled_modifier_ignored():
    v, var, applied = apply(0.3, 1.0, cohorts=[_cohort()], modifiers=[_mod(enabled=False)])
    assert (v, var, applied) == (0.3, 1.0, False)


def test_modifier_without_matching_consented_cohort_ignored():
    # consented to age_band but modifier targets reported_gender -> no match
    v, var, applied = apply(
        0.3,
        1.0,
        cohorts=[_cohort(key="age_band", value="25-34")],
        modifiers=[_mod(cohort_key="reported_gender", cohort_value="f")],
    )
    assert applied is False
    assert (v, var) == (0.3, 1.0)


def test_value_shift_clamped_to_max_abs_shift():
    # value_shift 0.4 but cap 0.05 -> only +0.05 applied
    v, var, applied = apply(
        0.3, 1.0, cohorts=[_cohort()], modifiers=[_mod(value_shift=0.4, max_abs_shift=0.05)]
    )
    assert applied is True
    assert v == pytest.approx(0.35)


def test_negative_value_shift_clamped():
    v, var, applied = apply(
        0.3, 1.0, cohorts=[_cohort()], modifiers=[_mod(value_shift=-0.4, max_abs_shift=0.05)]
    )
    assert v == pytest.approx(0.25)
    assert applied is True


def test_variance_scale_below_one_rejected_cannot_narrow():
    # variance_scale 0.5 would narrow -> rejected; variance unchanged.
    v, var, applied = apply(
        0.3, 1.0, cohorts=[_cohort()], modifiers=[_mod(variance_scale=0.5, value_shift=0.0)]
    )
    assert var == 1.0  # not narrowed
    # value unchanged and no scale applied; nothing effective -> applied False
    assert v == pytest.approx(0.3)
    assert applied is False


def test_variance_scale_widens():
    v, var, applied = apply(
        0.3, 1.0, cohorts=[_cohort()], modifiers=[_mod(variance_scale=2.0, value_shift=0.0)]
    )
    assert var == pytest.approx(2.0)
    assert applied is True


def test_multiple_matching_modifiers_accumulate_shift_and_compound_variance():
    mods = [
        _mod(cohort_key="age_band", cohort_value="25-34", value_shift=0.05, max_abs_shift=0.1, variance_scale=1.5),
        _mod(cohort_key="reported_gender", cohort_value="f", value_shift=0.05, max_abs_shift=0.1, variance_scale=2.0),
    ]
    cohorts = [
        _cohort(key="age_band", value="25-34"),
        _cohort(key="reported_gender", value="f"),
    ]
    v, var, applied = apply(0.3, 1.0, cohorts=cohorts, modifiers=mods)
    assert applied is True
    assert v == pytest.approx(0.4)        # 0.3 + 0.05 + 0.05
    assert var == pytest.approx(3.0)      # 1.0 * 1.5 * 2.0


def test_value_unchanged_when_axis_mismatch_is_callers_job():
    # apply() does not filter by axis (caller passes only this axis's modifiers);
    # so a modifier with a matching cohort still applies. Document that contract.
    v, var, applied = apply(0.3, 1.0, cohorts=[_cohort()], modifiers=[_mod(value_shift=0.02, max_abs_shift=0.1)])
    assert applied is True
    assert v == pytest.approx(0.32)
