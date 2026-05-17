"""End-to-end integration tests for the Lullaby analysis pipeline."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.figure
import numpy as np
import pytest

from lullaby.loader import generate_mock_session, load_session, load_all_sessions
from lullaby.features import align_to_epochs
from lullaby.statistics import compare_rem_vs_non_rem, compute_correlations, stage_transition_analysis
from lullaby.quality import assess_quality
from lullaby.visualization import plot_night_overview, plot_feature_distributions, plot_epoch_heatmap

# Phase 2 imports
from lullaby.temporal_features import add_temporal_features
from lullaby.pipeline import (
    prepare_sessions, split_by_session, generate_mock_dataset,
    make_binary_labels, STAGE_TO_INT,
)
from lullaby.model import XGBConfig, train_multiclass, train_binary_rem, cross_validate
from lullaby.evaluation import (
    compute_metrics, check_success_criteria, predict,
    plot_confusion_matrix, plot_feature_importance, print_metrics_report,
)
from lullaby.export import save_model, load_model


@pytest.mark.integration
class TestEndToEnd:
    """Full pipeline integration tests."""

    def test_mock_to_epochs_to_stats(self):
        """Mock -> epochs -> REM statistics -> verify sensible results."""
        session = generate_mock_session(duration_hours=8.0, seed=42)
        epochs = align_to_epochs(session)
        stats = compare_rem_vs_non_rem(epochs)

        assert len(epochs) > 0
        assert not stats.empty
        # Should have p-values for multiple features
        assert len(stats) >= 3

    def test_json_roundtrip_to_epochs(self, tmp_path):
        """Mock -> save JSON -> load -> epochs -> verify epoch count."""
        session = generate_mock_session(
            duration_hours=2.0, seed=42, save_json=True,
            output_path=tmp_path / "roundtrip.json",
        )
        loaded = load_session(tmp_path / "roundtrip.json")
        epochs_orig = align_to_epochs(session)
        epochs_loaded = align_to_epochs(loaded)

        assert len(epochs_orig) == len(epochs_loaded)

    def test_quality_to_epochs_to_correlations(self):
        """Mock -> quality -> epochs -> correlations (no crash)."""
        session = generate_mock_session(duration_hours=4.0, seed=77)
        report = assess_quality(session)
        assert report["overview"]["duration_hours"] == 4.0

        epochs = align_to_epochs(session)
        corr = compute_correlations(epochs)
        assert corr.shape[0] > 0

    def test_all_three_plots(self):
        """Mock -> epochs -> all 3 plots -> all return Figure."""
        session = generate_mock_session(duration_hours=4.0, seed=55)
        epochs = align_to_epochs(session)

        fig1 = plot_night_overview(session)
        fig2 = plot_feature_distributions(epochs)
        fig3 = plot_epoch_heatmap(epochs)

        assert isinstance(fig1, matplotlib.figure.Figure)
        assert isinstance(fig2, matplotlib.figure.Figure)
        assert isinstance(fig3, matplotlib.figure.Figure)

    def test_batch_load_and_analyze(self, tmp_path):
        """3 mock JSONs -> load all -> epochs each -> stats each."""
        for i, seed in enumerate([10, 20, 30]):
            generate_mock_session(
                duration_hours=2.0, seed=seed, save_json=True,
                output_path=tmp_path / f"session_{i}.json",
            )
        sessions = load_all_sessions(tmp_path)
        assert len(sessions) == 3

        for session in sessions:
            epochs = align_to_epochs(session)
            assert len(epochs) > 0
            transitions = stage_transition_analysis(epochs)
            assert isinstance(transitions, dict)

    def test_empty_session_full_pipeline(self, empty_session):
        """Empty session -> quality + epochs + stats + viz -> no crashes."""
        report = assess_quality(empty_session)
        assert report["heart_rate"]["actual_count"] == 0

        epochs = align_to_epochs(empty_session)
        assert len(epochs) > 0  # 8h duration → epochs exist (all NaN)

        stats = compare_rem_vs_non_rem(epochs)
        assert stats.empty  # No data → no stats

        fig1 = plot_night_overview(empty_session)
        fig2 = plot_feature_distributions(epochs)
        fig3 = plot_epoch_heatmap(epochs)
        assert isinstance(fig1, matplotlib.figure.Figure)
        assert isinstance(fig2, matplotlib.figure.Figure)
        assert isinstance(fig3, matplotlib.figure.Figure)


@pytest.mark.integration
class TestPhase2EndToEnd:
    """Phase 2 classification pipeline integration tests."""

    def test_mock_sessions_to_trained_model(self):
        """Multiple mock sessions -> pipeline -> train -> predict -> metrics."""
        sessions = [generate_mock_session(duration_hours=2.0, seed=i) for i in range(3)]
        dataset = prepare_sessions(sessions, min_coverage_pct=0.0)

        model = train_multiclass(dataset, config=XGBConfig(n_estimators=50))
        preds = predict(model, dataset)
        metrics = compute_metrics(dataset.y, preds)

        assert metrics.accuracy > 0
        assert 0 <= metrics.rem_f1 <= 1

    def test_binary_rem_pipeline(self):
        """Mock dataset -> binary REM training -> success criteria check."""
        dataset = generate_mock_dataset(n_sessions=3, duration_hours=2.0, base_seed=50)

        model = train_binary_rem(dataset, config=XGBConfig(n_estimators=50))
        y_binary = make_binary_labels(dataset.y)
        preds = predict(model, dataset)
        metrics = compute_metrics(y_binary, preds, binary=True)
        criteria = check_success_criteria(metrics)

        assert isinstance(criteria.passed, bool)

    def test_cross_validation_pipeline(self):
        """Mock dataset -> leave-one-out CV -> aggregate metrics."""
        dataset = generate_mock_dataset(n_sessions=3, duration_hours=2.0, base_seed=70)
        result = cross_validate(dataset, config=XGBConfig(n_estimators=30))

        assert len(result.fold_metrics) == 3
        assert 0 <= result.mean_metrics["rem_f1"] <= 1

    def test_save_load_predict_roundtrip(self, tmp_path):
        """Train -> save -> load -> predict -> same results."""
        dataset = generate_mock_dataset(n_sessions=2, duration_hours=2.0, base_seed=90)
        model = train_multiclass(dataset, config=XGBConfig(n_estimators=30))

        preds_original = predict(model, dataset)
        save_model(model, tmp_path / "model_v1")
        loaded, _ = load_model(tmp_path / "model_v1")
        preds_loaded = loaded.model.predict(dataset.X)

        np.testing.assert_array_equal(preds_original, preds_loaded)

    def test_full_reporting_pipeline(self):
        """Train -> metrics -> plots -> report (no crashes)."""
        dataset = generate_mock_dataset(n_sessions=3, duration_hours=2.0, base_seed=110)
        model = train_multiclass(dataset, config=XGBConfig(n_estimators=30))
        preds = predict(model, dataset)
        metrics = compute_metrics(dataset.y, preds)
        criteria = check_success_criteria(metrics)

        fig = plot_confusion_matrix(metrics)
        assert isinstance(fig, matplotlib.figure.Figure)

        fig2 = plot_feature_importance(model)
        assert isinstance(fig2, matplotlib.figure.Figure)

        report = print_metrics_report(metrics, criteria)
        assert "CLASSIFICATION REPORT" in report
