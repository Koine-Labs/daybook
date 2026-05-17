"""Tests for temporal feature engineering."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lullaby.features import align_to_epochs, get_feature_columns
from lullaby.temporal_features import (
    TemporalFeatureConfig,
    add_temporal_features,
    get_temporal_feature_names,
    DEFAULT_CONFIG,
    _BASE_FEATURES,
    _AUDIO_CLASSES,
)


class TestAddTemporalFeatures:
    """Tests for add_temporal_features()."""

    def test_returns_copy(self, epochs_df):
        """Original DataFrame should not be modified."""
        original_cols = list(epochs_df.columns)
        result = add_temporal_features(epochs_df)
        assert list(epochs_df.columns) == original_cols
        assert len(result.columns) > len(original_cols)

    def test_adds_rolling_mean_columns(self, epochs_df):
        result = add_temporal_features(epochs_df)
        for win in (3, 5):
            for feat in _BASE_FEATURES:
                col = f"{feat}_roll{win}_mean"
                assert col in result.columns, f"Missing {col}"

    def test_adds_rolling_std_columns(self, epochs_df):
        result = add_temporal_features(epochs_df)
        for win in (3, 5):
            for feat in _BASE_FEATURES:
                col = f"{feat}_roll{win}_std"
                assert col in result.columns, f"Missing {col}"

    def test_adds_delta_columns(self, epochs_df):
        result = add_temporal_features(epochs_df)
        for feat in _BASE_FEATURES:
            col = f"{feat}_delta"
            assert col in result.columns, f"Missing {col}"

    def test_adds_time_of_night(self, epochs_df):
        result = add_temporal_features(epochs_df)
        assert "time_of_night" in result.columns
        assert result["time_of_night"].min() >= 0.0
        assert result["time_of_night"].max() <= 1.0

    def test_adds_audio_onehot(self, epochs_df):
        result = add_temporal_features(epochs_df)
        for cls in _AUDIO_CLASSES:
            col = f"audio_is_{cls}"
            assert col in result.columns
            assert set(result[col].unique()).issubset({0.0, 1.0})

    def test_adds_iev_columns(self, epochs_df):
        result = add_temporal_features(epochs_df)
        for win in (3, 5):
            assert f"hr_mean_iev_{win}" in result.columns

    def test_no_nans_with_default_fill(self, epochs_df):
        result = add_temporal_features(epochs_df)
        numeric = result.select_dtypes(include=[np.number])
        assert not numeric.isna().any().any(), "NaN found in numeric columns"

    def test_feature_count_matches_expected(self, epochs_df):
        result = add_temporal_features(epochs_df)
        expected_names = get_temporal_feature_names()
        new_cols = set(result.columns) - set(epochs_df.columns)
        for name in expected_names:
            assert name in new_cols, f"Expected temporal feature {name} not found"

    def test_empty_dataframe(self):
        empty = pd.DataFrame()
        result = add_temporal_features(empty)
        assert result.empty

    def test_single_epoch(self, mock_session):
        epochs = align_to_epochs(mock_session)
        single = epochs.iloc[:1].copy()
        result = add_temporal_features(single)
        assert len(result) == 1
        # Rolling with min_periods=1 should still work
        numeric = result.select_dtypes(include=[np.number])
        assert not numeric.isna().any().any()

    def test_row_count_preserved(self, epochs_df):
        result = add_temporal_features(epochs_df)
        assert len(result) == len(epochs_df)


class TestTemporalFeatureConfig:
    """Tests for configuration options."""

    def test_disable_rolling_mean(self, epochs_df):
        config = TemporalFeatureConfig(enable_rolling_mean=False)
        result = add_temporal_features(epochs_df, config=config)
        rolling_mean_cols = [c for c in result.columns if "_roll" in c and c.endswith("_mean") and "iev" not in c]
        assert len(rolling_mean_cols) == 0

    def test_disable_deltas(self, epochs_df):
        config = TemporalFeatureConfig(enable_deltas=False)
        result = add_temporal_features(epochs_df, config=config)
        delta_cols = [c for c in result.columns if c.endswith("_delta")]
        assert len(delta_cols) == 0

    def test_custom_windows(self, epochs_df):
        config = TemporalFeatureConfig(rolling_windows=(2, 7))
        result = add_temporal_features(epochs_df, config=config)
        assert "hr_mean_roll2_mean" in result.columns
        assert "hr_mean_roll7_mean" in result.columns
        assert "hr_mean_roll3_mean" not in result.columns

    def test_zero_fill_strategy(self, epochs_df):
        config = TemporalFeatureConfig(fill_strategy="zero")
        result = add_temporal_features(epochs_df, config=config)
        numeric = result.select_dtypes(include=[np.number])
        assert not numeric.isna().any().any()


class TestGetTemporalFeatureNames:
    """Tests for get_temporal_feature_names()."""

    def test_default_count(self):
        names = get_temporal_feature_names()
        # 5 base × 2 windows × 2 (mean+std) = 20 rolling
        # 5 deltas + 1 time_of_night + 4 audio + 2 iev = 12
        assert len(names) == 32

    def test_matches_actual_features(self, epochs_df):
        expected = set(get_temporal_feature_names())
        result = add_temporal_features(epochs_df)
        actual_new = set(result.columns) - set(epochs_df.columns)
        assert expected == actual_new
