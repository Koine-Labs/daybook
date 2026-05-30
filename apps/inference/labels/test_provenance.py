from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labels.provenance import TRUST_ORDER, LabelSource, classify_source

# The exact #17 source set — drift here means commitment #17 changed.
EXPECTED_SOURCES = {
    "ground_truth",
    "self_report",
    "observed_outcome",
    "heuristic",
    "literature_prior",
    "demographic_prior",
    "llm_literature_bootstrap",
    "clinician",
}


def test_enum_is_exactly_the_eight_17_sources():
    assert {m.value for m in LabelSource} == EXPECTED_SOURCES
    assert len(list(LabelSource)) == 8


def test_label_source_is_str_enum():
    assert LabelSource.SELF_REPORT == "self_report"
    assert isinstance(LabelSource.SELF_REPORT, str)


def test_trust_order_is_a_complete_ordering():
    assert isinstance(TRUST_ORDER, tuple)
    assert set(TRUST_ORDER) == set(LabelSource)
    assert len(TRUST_ORDER) == len(set(TRUST_ORDER)) == 8
    assert TRUST_ORDER[0] is LabelSource.GROUND_TRUTH


def test_classify_source_maps_exact_enum_values():
    for member in LabelSource:
        assert classify_source(member.value) is member


def test_classify_source_defaults_unknown_to_heuristic():
    assert classify_source("some.unknown.device.tag") is LabelSource.HEURISTIC
    assert classify_source("") is LabelSource.HEURISTIC


def test_classify_source_handles_case_insensitively():
    assert classify_source("SELF_REPORT") is LabelSource.SELF_REPORT
