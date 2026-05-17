"""Tests for lullaby.visualization — all 3 plot types render without crashing."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.figure

from lullaby.visualization import (
    plot_night_overview,
    plot_feature_distributions,
    plot_epoch_heatmap,
)
from lullaby.features import align_to_epochs


# =====================================================================
# plot_night_overview() tests
# =====================================================================

class TestPlotNightOverview:
    """Tests for plot_night_overview()."""

    def test_happy_path(self, mock_session):
        fig = plot_night_overview(mock_session)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_empty_session(self, empty_session):
        fig = plot_night_overview(empty_session)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_single_sample(self, single_sample_session):
        fig = plot_night_overview(single_sample_session)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_custom_figsize(self, short_session):
        fig = plot_night_overview(short_session, figsize=(10, 8))
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_with_precomputed_epochs(self, mock_session, epochs_df):
        fig = plot_night_overview(mock_session, epochs=epochs_df)
        assert isinstance(fig, matplotlib.figure.Figure)


# =====================================================================
# plot_feature_distributions() tests
# =====================================================================

class TestPlotFeatureDistributions:
    """Tests for plot_feature_distributions()."""

    def test_happy_path(self, epochs_df):
        fig = plot_feature_distributions(epochs_df)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_empty_epochs(self):
        """Empty DataFrame with correct schema → renders placeholder."""
        epochs = pd.DataFrame({
            "epoch_start": pd.Series(dtype="float64"),
            "epoch_end": pd.Series(dtype="float64"),
            "epoch_time_hours": pd.Series(dtype="float64"),
            "hr_mean": pd.Series(dtype="float64"),
            "sleep_stage": pd.Series(dtype="object"),
            "dominant_classification": pd.Series(dtype="object"),
            "hr_count": pd.Series(dtype="int64"),
            "motion_count": pd.Series(dtype="int64"),
        })
        fig = plot_feature_distributions(epochs)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_no_valid_stages(self):
        """Epochs where all sleep_stage values are None."""
        epochs = pd.DataFrame({
            "epoch_start": [0, 30],
            "epoch_end": [30, 60],
            "epoch_time_hours": [0.004, 0.013],
            "hr_mean": [70.0, 72.0],
            "hr_std": [2.0, 3.0],
            "sleep_stage": [None, None],
            "dominant_classification": [None, None],
            "hr_count": [6, 6],
            "motion_count": [0, 0],
        })
        fig = plot_feature_distributions(epochs)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_custom_feature_list(self, epochs_df):
        fig = plot_feature_distributions(epochs_df, features=["hr_mean", "hrv_mean"])
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_single_feature(self, epochs_df):
        fig = plot_feature_distributions(epochs_df, features=["hr_mean"])
        assert isinstance(fig, matplotlib.figure.Figure)


# =====================================================================
# plot_epoch_heatmap() tests
# =====================================================================

class TestPlotEpochHeatmap:
    """Tests for plot_epoch_heatmap()."""

    def test_happy_path(self, epochs_df):
        fig = plot_epoch_heatmap(epochs_df)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_std_zero_no_crash(self):
        """When a feature column has std=0, z-scoring produces NaN → should be filled with 0."""
        epochs = pd.DataFrame({
            "epoch_start": range(5),
            "epoch_end": range(1, 6),
            "epoch_time_hours": [i / 120 for i in range(5)],
            "hr_mean": [70.0] * 5,  # All same → std=0
            "hrv_mean": [50.0] * 5,
            "sleep_stage": ["coreLight"] * 5,
            "dominant_classification": [None] * 5,
            "hr_count": [6] * 5,
            "motion_count": [0] * 5,
        })
        fig = plot_epoch_heatmap(epochs)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_all_nan_features(self):
        """When all features are NaN, should still render."""
        epochs = pd.DataFrame({
            "epoch_start": range(3),
            "epoch_end": range(1, 4),
            "epoch_time_hours": [i / 120 for i in range(3)],
            "hr_mean": [np.nan] * 3,
            "hrv_mean": [np.nan] * 3,
            "sleep_stage": [None] * 3,
            "dominant_classification": [None] * 3,
            "hr_count": [0] * 3,
            "motion_count": [0] * 3,
        })
        fig = plot_epoch_heatmap(epochs)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_single_epoch(self):
        epochs = pd.DataFrame({
            "epoch_start": [0],
            "epoch_end": [30],
            "epoch_time_hours": [0.004],
            "hr_mean": [70.0],
            "hrv_mean": [50.0],
            "sleep_stage": ["coreLight"],
            "dominant_classification": [None],
            "hr_count": [6],
            "motion_count": [0],
        })
        fig = plot_epoch_heatmap(epochs)
        assert isinstance(fig, matplotlib.figure.Figure)
