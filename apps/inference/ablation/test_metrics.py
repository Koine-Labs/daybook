"""Metrics — known-input → known-output, pure numpy, DB-free + LLM-free."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from ablation.metrics import (
    LOWER_IS_BETTER,
    auroc,
    brier_binary,
    crps_gaussian,
    expected_calibration_error,
    is_better,
    multiclass_brier,
    multiclass_log_loss,
    nll_gaussian,
)


def test_brier_binary_perfect() -> None:
    assert brier_binary([1.0, 0.0], [1, 0]) == 0.0


def test_brier_binary_known() -> None:
    # preds 0.5,0.5 vs labels 1,0 -> mean((0.5)^2,(0.5)^2)=0.25
    assert brier_binary([0.5, 0.5], [1, 0]) == 0.25


def test_multiclass_brier_known() -> None:
    probs = [[1.0, 0.0], [0.0, 1.0]]
    labels = [0, 1]
    assert multiclass_brier(probs, labels) == 0.0
    probs2 = [[0.5, 0.5]]
    labels2 = [0]
    # (0.5-1)^2 + (0.5-0)^2 = 0.5
    assert abs(multiclass_brier(probs2, labels2) - 0.5) < 1e-9


def test_multiclass_log_loss_known() -> None:
    probs = [[0.5, 0.5]]
    labels = [0]
    assert abs(multiclass_log_loss(probs, labels) - (-math.log(0.5))) < 1e-9


def test_log_loss_clips_zero() -> None:
    # a 0-prob on the true class must not be inf
    val = multiclass_log_loss([[0.0, 1.0]], [0])
    assert math.isfinite(val)
    assert val > 0


def test_nll_gaussian_known() -> None:
    # single point at the mean, sigma=1: nll = 0.5*log(2pi)
    val = nll_gaussian([0.0], [0.0], [1.0])
    assert abs(val - 0.5 * math.log(2 * math.pi)) < 1e-9


def test_crps_gaussian_perfect_is_small() -> None:
    # tight prediction exactly on target -> small CRPS
    tight = crps_gaussian([0.0], [0.0], [1e-3])
    loose = crps_gaussian([0.0], [0.0], [10.0])
    assert tight < loose


def test_auroc_perfect_separation() -> None:
    scores = [0.1, 0.2, 0.8, 0.9]
    labels = [0, 0, 1, 1]
    assert abs(auroc(scores, labels) - 1.0) < 1e-9


def test_auroc_inverted() -> None:
    scores = [0.9, 0.8, 0.2, 0.1]
    labels = [0, 0, 1, 1]
    assert abs(auroc(scores, labels) - 0.0) < 1e-9


def test_auroc_single_class_returns_nan() -> None:
    assert math.isnan(auroc([0.1, 0.2], [1, 1]))


def test_ece_perfect_calibration() -> None:
    # confidences match accuracy exactly within each bin -> ~0
    preds = [0.0, 0.0, 1.0, 1.0]
    labels = [0, 0, 1, 1]
    assert expected_calibration_error(preds, labels, n_bins=2) == 0.0


def test_ece_miscalibrated() -> None:
    preds = [0.9, 0.9]
    labels = [0, 0]
    # confident-but-wrong -> ECE near 0.9
    assert expected_calibration_error(preds, labels, n_bins=5) > 0.8


def test_lower_is_better_membership() -> None:
    assert "brier" in LOWER_IS_BETTER
    assert "nll" in LOWER_IS_BETTER
    assert "crps" in LOWER_IS_BETTER
    assert "calibration_error" in LOWER_IS_BETTER
    assert "log_loss" in LOWER_IS_BETTER
    assert "auroc" not in LOWER_IS_BETTER


def test_is_better_sign_normalization() -> None:
    # lower-is-better metric: smaller wins
    assert is_better("brier", 0.1, 0.2) is True
    assert is_better("brier", 0.3, 0.2) is False
    # higher-is-better metric: larger wins
    assert is_better("auroc", 0.9, 0.8) is True
    assert is_better("auroc", 0.7, 0.8) is False


def test_is_better_with_delta_margin() -> None:
    # must beat by delta to count
    assert is_better("brier", 0.18, 0.20, delta=0.05) is False
    assert is_better("brier", 0.14, 0.20, delta=0.05) is True
    assert is_better("auroc", 0.82, 0.80, delta=0.05) is False
    assert is_better("auroc", 0.86, 0.80, delta=0.05) is True
