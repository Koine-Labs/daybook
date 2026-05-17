"""Tests for model evaluation and visualization."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.figure
import matplotlib.pyplot as plt
import numpy as np
import pytest

from lullaby.pipeline import (
    ClassificationDataset,
    STAGE_TO_INT,
    INT_TO_STAGE,
    make_binary_labels,
)
from lullaby.model import (
    XGBConfig,
    TrainedModel,
    CVResult,
    train_multiclass,
    train_binary_rem,
    cross_validate,
)
from lullaby.evaluation import (
    ClassificationMetrics,
    SuccessCriteria,
    compute_metrics,
    compute_rem_onset_latency,
    check_success_criteria,
    predict,
    print_metrics_report,
    plot_confusion_matrix,
    plot_hypnogram_comparison,
    plot_feature_importance,
    plot_shap_summary,
    plot_cv_results,
    _find_contiguous_bouts,
)


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------

class TestComputeMetrics:
    """Tests for compute_metrics()."""

    def test_perfect_predictions(self):
        y = np.array([0, 1, 2, 3, 4])
        metrics = compute_metrics(y, y)
        assert metrics.accuracy == 1.0
        assert metrics.cohens_kappa == 1.0

    def test_all_wrong(self):
        y_true = np.array([0, 0, 0, 0])
        y_pred = np.array([1, 1, 1, 1])
        metrics = compute_metrics(y_true, y_pred)
        assert metrics.accuracy == 0.0

    def test_rem_metrics_present(self):
        y_true = np.array([0, 1, 1, 2, 3])
        y_pred = np.array([0, 1, 0, 2, 3])
        metrics = compute_metrics(y_true, y_pred)
        assert 0 <= metrics.rem_precision <= 1
        assert 0 <= metrics.rem_recall <= 1
        assert 0 <= metrics.rem_f1 <= 1

    def test_confusion_matrix_shape(self):
        y_true = np.array([0, 1, 2, 0, 1, 2])
        y_pred = np.array([0, 1, 1, 0, 2, 2])
        metrics = compute_metrics(y_true, y_pred)
        n = len(set(y_true) | set(y_pred))
        assert metrics.confusion.shape == (n, n)

    def test_binary_metrics(self):
        y_true = np.array([0, 1, 1, 0, 0])
        y_pred = np.array([0, 1, 0, 0, 1])
        metrics = compute_metrics(y_true, y_pred, binary=True)
        assert "REM" in metrics.per_class_f1 or "non-REM" in metrics.per_class_f1

    def test_per_class_metrics_all_classes(self):
        y_true = np.array([0, 1, 2, 3, 4])
        y_pred = np.array([0, 1, 2, 3, 4])
        metrics = compute_metrics(y_true, y_pred)
        for name in INT_TO_STAGE.values():
            assert name in metrics.per_class_f1

    def test_macro_weighted_f1_range(self):
        y_true = np.array([0, 1, 2, 1, 0])
        y_pred = np.array([0, 1, 1, 1, 0])
        metrics = compute_metrics(y_true, y_pred)
        assert 0 <= metrics.macro_f1 <= 1
        assert 0 <= metrics.weighted_f1 <= 1


class TestComputeRemOnsetLatency:
    """Tests for compute_rem_onset_latency()."""

    def test_perfect_detection(self):
        y_true = np.array([0, 0, 1, 1, 1, 0, 0])
        y_pred = np.array([0, 0, 1, 1, 1, 0, 0])
        latency = compute_rem_onset_latency(y_true, y_pred)
        assert latency == 0.0

    def test_delayed_detection(self):
        y_true = np.array([0, 0, 1, 1, 1, 0])
        y_pred = np.array([0, 0, 0, 1, 1, 0])
        latency = compute_rem_onset_latency(y_true, y_pred)
        assert latency == 1.0  # Detected 1 epoch late

    def test_undetected_bout(self):
        y_true = np.array([0, 0, 1, 1, 1, 0])
        y_pred = np.array([0, 0, 0, 0, 0, 0])
        latency = compute_rem_onset_latency(y_true, y_pred)
        assert latency == 3.0  # Penalty = bout length

    def test_no_rem_bouts(self):
        y_true = np.array([0, 0, 0, 0])
        y_pred = np.array([0, 0, 0, 0])
        latency = compute_rem_onset_latency(y_true, y_pred)
        assert latency is None

    def test_multiple_bouts(self):
        y_true = np.array([1, 1, 0, 0, 1, 1, 1])
        y_pred = np.array([0, 1, 0, 0, 1, 1, 1])
        latency = compute_rem_onset_latency(y_true, y_pred)
        # Bout 1: latency=1, Bout 2: latency=0 → mean=0.5
        assert latency == 0.5


class TestCheckSuccessCriteria:
    """Tests for check_success_criteria()."""

    def test_all_pass(self):
        metrics = _make_metrics(rem_p=0.80, rem_r=0.70, rem_f=0.75)
        criteria = check_success_criteria(metrics)
        assert criteria.passed is True

    def test_precision_fail(self):
        metrics = _make_metrics(rem_p=0.50, rem_r=0.70, rem_f=0.59)
        criteria = check_success_criteria(metrics)
        assert criteria.rem_precision_met is False
        assert criteria.passed is False

    def test_recall_fail(self):
        metrics = _make_metrics(rem_p=0.80, rem_r=0.50, rem_f=0.62)
        criteria = check_success_criteria(metrics)
        assert criteria.rem_recall_met is False
        assert criteria.passed is False

    def test_f1_fail(self):
        metrics = _make_metrics(rem_p=0.70, rem_r=0.60, rem_f=0.60)
        criteria = check_success_criteria(metrics)
        assert criteria.rem_f1_met is False
        assert criteria.passed is False

    def test_custom_targets(self):
        metrics = _make_metrics(rem_p=0.50, rem_r=0.50, rem_f=0.50)
        criteria = check_success_criteria(metrics, precision_target=0.50, recall_target=0.50, f1_target=0.50)
        assert criteria.passed is True


class TestPredict:
    """Tests for predict()."""

    def test_multiclass_predict(self, small_dataset):
        model = train_multiclass(small_dataset, config=XGBConfig(n_estimators=20))
        preds = predict(model, small_dataset)
        assert len(preds) == len(small_dataset.y)
        assert preds.dtype == np.int64

    def test_binary_predict(self, small_dataset):
        model = train_binary_rem(small_dataset, config=XGBConfig(n_estimators=20))
        preds = predict(model, small_dataset)
        assert set(preds).issubset({0, 1})


# ---------------------------------------------------------------------------
# Visualization tests
# ---------------------------------------------------------------------------

class TestPlotConfusionMatrix:
    """Tests for plot_confusion_matrix()."""

    def test_returns_figure(self):
        metrics = _make_metrics()
        fig = plot_confusion_matrix(metrics)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_normalized(self):
        metrics = _make_metrics()
        fig = plot_confusion_matrix(metrics, normalize=True)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_unnormalized(self):
        metrics = _make_metrics()
        fig = plot_confusion_matrix(metrics, normalize=False)
        assert isinstance(fig, matplotlib.figure.Figure)


class TestPlotHypnogramComparison:
    """Tests for plot_hypnogram_comparison()."""

    def test_returns_figure(self):
        y = np.array([0, 1, 2, 3, 1, 0])
        fig = plot_hypnogram_comparison(y, y)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_different_predictions(self):
        y_true = np.array([0, 1, 2, 3])
        y_pred = np.array([0, 0, 2, 3])
        fig = plot_hypnogram_comparison(y_true, y_pred)
        assert isinstance(fig, matplotlib.figure.Figure)


class TestPlotFeatureImportance:
    """Tests for plot_feature_importance()."""

    def test_returns_figure(self, small_dataset):
        model = train_multiclass(small_dataset, config=XGBConfig(n_estimators=20))
        fig = plot_feature_importance(model)
        assert isinstance(fig, matplotlib.figure.Figure)


class TestPlotShapSummary:
    """Tests for plot_shap_summary()."""

    @pytest.mark.slow
    def test_returns_figure(self, small_dataset):
        model = train_multiclass(small_dataset, config=XGBConfig(n_estimators=20))
        fig = plot_shap_summary(model, small_dataset, max_samples=50)
        assert isinstance(fig, matplotlib.figure.Figure)


class TestPlotCVResults:
    """Tests for plot_cv_results()."""

    def test_returns_figure(self, small_dataset):
        result = cross_validate(small_dataset, config=XGBConfig(n_estimators=20))
        fig = plot_cv_results(result)
        assert isinstance(fig, matplotlib.figure.Figure)


# ---------------------------------------------------------------------------
# Reporting tests
# ---------------------------------------------------------------------------

class TestPrintMetricsReport:
    """Tests for print_metrics_report()."""

    def test_returns_string(self):
        metrics = _make_metrics()
        report = print_metrics_report(metrics)
        assert isinstance(report, str)
        assert "CLASSIFICATION REPORT" in report

    def test_with_criteria(self):
        metrics = _make_metrics(rem_p=0.80, rem_r=0.70, rem_f=0.75)
        criteria = check_success_criteria(metrics)
        report = print_metrics_report(metrics, criteria)
        assert "PASS" in report


# ---------------------------------------------------------------------------
# Internal helpers tests
# ---------------------------------------------------------------------------

class TestFindContiguousBouts:
    """Tests for _find_contiguous_bouts()."""

    def test_single_bout(self):
        y = np.array([0, 0, 1, 1, 1, 0])
        bouts = _find_contiguous_bouts(y, 1)
        assert bouts == [(2, 5)]

    def test_multiple_bouts(self):
        y = np.array([1, 1, 0, 1, 1, 1])
        bouts = _find_contiguous_bouts(y, 1)
        assert bouts == [(0, 2), (3, 6)]

    def test_no_bouts(self):
        y = np.array([0, 0, 0])
        bouts = _find_contiguous_bouts(y, 1)
        assert bouts == []


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_metrics(
    rem_p: float = 0.75,
    rem_r: float = 0.65,
    rem_f: float = 0.70,
) -> ClassificationMetrics:
    """Create a ClassificationMetrics for testing."""
    return ClassificationMetrics(
        accuracy=0.75,
        per_class_precision={"remSleep": rem_p, "coreLight": 0.80},
        per_class_recall={"remSleep": rem_r, "coreLight": 0.85},
        per_class_f1={"remSleep": rem_f, "coreLight": 0.82},
        macro_f1=0.70,
        weighted_f1=0.72,
        confusion=np.array([[10, 2], [3, 8]]),
        confusion_labels=["remSleep", "coreLight"],
        cohens_kappa=0.65,
        rem_precision=rem_p,
        rem_recall=rem_r,
        rem_f1=rem_f,
        rem_onset_latency=None,
    )
