"""Tests for lullaby.statistics — REM vs non-REM comparison, correlations, transitions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lullaby.statistics import (
    compare_rem_vs_non_rem,
    compute_correlations,
    stage_transition_analysis,
    format_statistics_table,
)
from lullaby.features import align_to_epochs


# =====================================================================
# compare_rem_vs_non_rem() tests
# =====================================================================

class TestCompareRemVsNonRem:
    """Tests for compare_rem_vs_non_rem()."""

    def test_returns_dataframe(self, epochs_df):
        result = compare_rem_vs_non_rem(epochs_df)
        assert isinstance(result, pd.DataFrame)

    def test_sorted_by_pvalue(self, epochs_df):
        result = compare_rem_vs_non_rem(epochs_df)
        if len(result) > 1:
            assert result["p_value"].is_monotonic_increasing

    def test_bonferroni_corrected_leq_1(self, epochs_df):
        result = compare_rem_vs_non_rem(epochs_df)
        if not result.empty:
            assert (result["p_corrected"] <= 1.0).all()
            assert (result["p_corrected"] >= 0.0).all()

    def test_effect_size_bounded(self, epochs_df):
        result = compare_rem_vs_non_rem(epochs_df)
        if not result.empty:
            assert (result["effect_size"] >= -1.0).all()
            assert (result["effect_size"] <= 1.0).all()

    def test_no_rem_returns_empty(self, no_rem_session):
        epochs = align_to_epochs(no_rem_session)
        result = compare_rem_vs_non_rem(epochs)
        assert result.empty

    def test_empty_epochs_returns_empty(self):
        """Empty DataFrame with correct schema → returns empty."""
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
        result = compare_rem_vs_non_rem(epochs)
        assert result.empty

    def test_required_columns_present(self, epochs_df):
        result = compare_rem_vs_non_rem(epochs_df)
        if not result.empty:
            expected_cols = [
                "feature", "rem_median", "non_rem_median",
                "u_statistic", "p_value", "p_corrected",
                "effect_size", "cohens_d", "significant",
            ]
            for col in expected_cols:
                assert col in result.columns, f"Missing column: {col}"

    def test_identical_values_cohens_d_zero(self):
        """If REM and non-REM have identical feature values, Cohen's d should be 0."""
        epochs = pd.DataFrame({
            "hr_mean": [70.0] * 20,
            "sleep_stage": ["remSleep"] * 10 + ["coreLight"] * 10,
            "epoch_start": range(20),
            "epoch_end": range(1, 21),
            "epoch_time_hours": [i / 120 for i in range(20)],
            "hr_count": [6] * 20,
            "motion_count": [0] * 20,
            "dominant_classification": [None] * 20,
        })
        result = compare_rem_vs_non_rem(epochs)
        if not result.empty:
            hr_row = result[result["feature"] == "hr_mean"]
            if not hr_row.empty:
                assert hr_row.iloc[0]["cohens_d"] == 0.0


# =====================================================================
# compute_correlations() tests
# =====================================================================

class TestComputeCorrelations:
    """Tests for compute_correlations()."""

    def test_returns_square_matrix(self, epochs_df):
        corr = compute_correlations(epochs_df)
        assert corr.shape[0] == corr.shape[1]

    def test_diagonal_is_one(self, epochs_df):
        corr = compute_correlations(epochs_df)
        for col in corr.columns:
            assert corr.loc[col, col] == pytest.approx(1.0, abs=0.001)

    def test_spearman_default(self, epochs_df):
        corr = compute_correlations(epochs_df)
        assert isinstance(corr, pd.DataFrame)

    def test_pearson_option(self, epochs_df):
        corr = compute_correlations(epochs_df, method="pearson")
        assert isinstance(corr, pd.DataFrame)
        assert corr.shape[0] == corr.shape[1]

    def test_empty_epochs(self):
        """Empty DataFrame → correlation matrix is all NaN (no data to correlate)."""
        epochs = pd.DataFrame({
            "epoch_start": pd.Series(dtype="float64"),
            "hr_mean": pd.Series(dtype="float64"),
            "sleep_stage": pd.Series(dtype="object"),
            "dominant_classification": pd.Series(dtype="object"),
            "hr_count": pd.Series(dtype="int64"),
            "motion_count": pd.Series(dtype="int64"),
        })
        corr = compute_correlations(epochs)
        # With 0 rows, corr matrix exists but all values are NaN
        assert corr.isna().all().all()


# =====================================================================
# stage_transition_analysis() tests
# =====================================================================

class TestStageTransitionAnalysis:
    """Tests for stage_transition_analysis()."""

    def test_returns_dict_with_expected_keys(self, epochs_df):
        result = stage_transition_analysis(epochs_df)
        expected_keys = {
            "transition_matrix", "transition_counts",
            "pre_rem_features", "post_rem_features", "rem_onset_count",
        }
        assert set(result.keys()) == expected_keys

    def test_transition_rows_sum_near_one(self, epochs_df):
        result = stage_transition_analysis(epochs_df)
        tm = result["transition_matrix"]
        if not tm.empty:
            row_sums = tm.sum(axis=1)
            for stage, total in row_sums.items():
                assert total == pytest.approx(1.0, abs=0.01), \
                    f"Transition row {stage} sums to {total}"

    def test_rem_onset_count_positive(self, epochs_df):
        result = stage_transition_analysis(epochs_df)
        # 8-hour mock session should have at least 1 REM onset
        assert result["rem_onset_count"] > 0

    def test_pre_rem_features_populated(self, epochs_df):
        result = stage_transition_analysis(epochs_df)
        if result["rem_onset_count"] > 0:
            assert not result["pre_rem_features"].empty

    def test_no_valid_stages_returns_empty(self):
        """Empty DataFrame with correct schema → empty transitions."""
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
        result = stage_transition_analysis(epochs)
        assert result["transition_matrix"].empty
        assert result["rem_onset_count"] == 0

    def test_single_epoch_returns_empty_transitions(self, single_sample_session):
        epochs = align_to_epochs(single_sample_session)
        result = stage_transition_analysis(epochs)
        # With only 1 epoch, there are no transitions
        assert result["transition_matrix"].empty or result["transition_counts"].sum().sum() == 0


# =====================================================================
# format_statistics_table() tests
# =====================================================================

class TestFormatStatisticsTable:
    """Tests for format_statistics_table()."""

    def test_empty_returns_message(self):
        result = format_statistics_table(pd.DataFrame())
        assert "No statistical comparisons" in result

    def test_non_empty_returns_multiline(self, epochs_df):
        stats = compare_rem_vs_non_rem(epochs_df)
        if not stats.empty:
            result = format_statistics_table(stats)
            lines = result.strip().split("\n")
            assert len(lines) >= 3  # header + separator + at least 1 row
