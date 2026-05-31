"""Truth-grader selection by TRUST_ORDER + proxy-grader stub contract (DB/LLM-free)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from labels import LabelSource
from ablation.dataset import GradedPair
from ablation.grader import (
    GROUND_TRUTH_GRADER,
    PROXY_GRADER,
    SELF_REPORT_GRADER,
    proxy_outcome_error,
    select_truth_grader,
)


def _pair(source: LabelSource) -> GradedPair:
    return GradedPair(
        observed_at=datetime.now(timezone.utc),
        truth_value=0.5,
        truth_source=source,
        truth_confidence=0.9,
        belief_inputs={"eeg": 0.5},
    )


def test_ground_truth_wins() -> None:
    pairs = [_pair(LabelSource.SELF_REPORT), _pair(LabelSource.GROUND_TRUTH)]
    assert select_truth_grader(pairs) == GROUND_TRUTH_GRADER


def test_clinician_maps_to_ground_truth_grader() -> None:
    pairs = [_pair(LabelSource.CLINICIAN), _pair(LabelSource.SELF_REPORT)]
    assert select_truth_grader(pairs) == GROUND_TRUTH_GRADER


def test_self_report_when_no_higher_tier() -> None:
    pairs = [_pair(LabelSource.SELF_REPORT), _pair(LabelSource.OBSERVED_OUTCOME)]
    assert select_truth_grader(pairs) == SELF_REPORT_GRADER


def test_observed_outcome_falls_to_proxy() -> None:
    pairs = [_pair(LabelSource.OBSERVED_OUTCOME)]
    assert select_truth_grader(pairs) == PROXY_GRADER


def test_empty_pairs_returns_proxy() -> None:
    assert select_truth_grader([]) == PROXY_GRADER


def test_trust_order_respected_full_mix() -> None:
    pairs = [
        _pair(LabelSource.OBSERVED_OUTCOME),
        _pair(LabelSource.SELF_REPORT),
        _pair(LabelSource.CLINICIAN),
    ]
    assert select_truth_grader(pairs) == GROUND_TRUTH_GRADER


def test_proxy_grader_is_documented_stub() -> None:
    # The proxy grader has a stable contract but is a labeled stub: it raises
    # NotImplementedError, never silently fakes an error signal.
    pairs = [_pair(LabelSource.OBSERVED_OUTCOME)]
    with pytest.raises(NotImplementedError):
        proxy_outcome_error(pairs, [0.5])
