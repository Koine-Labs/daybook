"""Tests for lullaby.features — epoch alignment and feature engineering."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lullaby.features import (
    align_to_epochs,
    get_feature_columns,
    _slice_by_timestamp,
    _majority_stage,
)
from lullaby.loader import SleepSessionData


# =====================================================================
# align_to_epochs() tests
# =====================================================================

class TestAlignToEpochs:
    """Tests for align_to_epochs()."""

    def test_correct_epoch_count(self, mock_session):
        epochs = align_to_epochs(mock_session)
        expected = int(np.ceil(mock_session.duration_hours * 3600 / 30))
        assert len(epochs) == expected

    def test_boundaries_start_at_zero(self, mock_session):
        epochs = align_to_epochs(mock_session)
        assert epochs.iloc[0]["epoch_start"] == 0.0

    def test_custom_epoch_size(self, short_session):
        epochs = align_to_epochs(short_session, epoch_seconds=60.0)
        expected = int(np.ceil(short_session.duration_hours * 3600 / 60))
        assert len(epochs) == expected
        assert epochs.iloc[0]["epoch_end"] == 60.0

    def test_hr_features_populated(self, mock_session):
        epochs = align_to_epochs(mock_session)
        # Most epochs should have HR data
        assert epochs["hr_mean"].notna().sum() > len(epochs) * 0.8
        # HR mean should be in physiological range
        valid_hr = epochs["hr_mean"].dropna()
        assert valid_hr.min() >= 40
        assert valid_hr.max() <= 120

    def test_empty_session_all_nan(self, empty_session):
        epochs = align_to_epochs(empty_session)
        # Duration is 8h → should have epochs
        assert len(epochs) == int(np.ceil(8 * 3600 / 30))
        # All HR values should be NaN
        assert epochs["hr_mean"].isna().all()
        # Sleep stage should be None
        assert epochs["sleep_stage"].isna().all()

    def test_zero_duration_no_epochs(self, zero_duration_session):
        epochs = align_to_epochs(zero_duration_session)
        assert len(epochs) == 0

    def test_single_sample_std_zero(self, single_sample_session):
        epochs = align_to_epochs(single_sample_session)
        # With one HR sample, std should be 0
        valid = epochs[epochs["hr_count"] > 0]
        if not valid.empty:
            assert valid.iloc[0]["hr_std"] == 0.0

    def test_hrv_forward_fill(self, mock_session):
        """HRV is sparse (~5min intervals), so ffill should reduce NaN count."""
        epochs = align_to_epochs(mock_session)
        # After forward-fill, there should be fewer NaN than without
        # First few epochs might still be NaN, but the rest should be filled
        assert epochs["hrv_mean"].notna().sum() > epochs["hrv_mean"].isna().sum()

    def test_no_sleep_stages_all_none(self):
        """Session with no sleep stages → all epoch stages are None."""
        session = SleepSessionData(
            session_id="no-stages",
            start_time=pd.Timestamp("2025-03-15 23:00:00", tz="UTC").to_pydatetime(),
            end_time=pd.Timestamp("2025-03-15 23:05:00", tz="UTC").to_pydatetime(),
            duration_hours=5 / 60,
            heart_rate=pd.DataFrame({"timestamp": [0.0, 100.0, 200.0], "bpm": [70, 72, 68]}),
            hrv=pd.DataFrame(columns=["timestamp", "sdnn"]),
            accelerometer=pd.DataFrame(columns=["timestamp", "x", "y", "z"]),
            sonar=pd.DataFrame(columns=["timestamp", "breathing_rate", "breathing_regularity", "signal_strength"]),
            audio=pd.DataFrame(columns=["timestamp", "dominant_frequency", "spectral_centroid", "rms_energy", "zcr", "classification"]),
            sleep_stages=pd.DataFrame(columns=["start", "end", "stage"]),
            metadata={},
        )
        epochs = align_to_epochs(session)
        assert epochs["sleep_stage"].isna().all()

    def test_epoch_columns_present(self, mock_session):
        epochs = align_to_epochs(mock_session)
        expected_cols = [
            "epoch_start", "epoch_end", "epoch_time_hours",
            "hr_mean", "hr_std", "hr_min", "hr_max", "hr_range", "hr_count",
            "hrv_mean",
            "accel_mag_mean", "accel_mag_std", "accel_mag_max", "motion_count",
            "breathing_rate_mean", "breathing_regularity_mean", "signal_strength_mean",
            "rms_energy_mean", "spectral_centroid_mean", "dominant_classification",
            "sleep_stage",
        ]
        for col in expected_cols:
            assert col in epochs.columns, f"Missing column: {col}"

    def test_sleep_stage_values_are_valid(self, mock_session):
        epochs = align_to_epochs(mock_session)
        valid_stages = {"remSleep", "deepSleep", "coreLight", "awake", "inBed"}
        non_null = epochs["sleep_stage"].dropna()
        for stage in non_null:
            assert stage in valid_stages, f"Invalid stage: {stage}"


# =====================================================================
# get_feature_columns() tests
# =====================================================================

class TestGetFeatureColumns:
    """Tests for get_feature_columns()."""

    def test_excludes_metadata(self, epochs_df):
        features = get_feature_columns(epochs_df)
        excluded = {"epoch_start", "epoch_end", "epoch_time_hours",
                    "sleep_stage", "dominant_classification",
                    "hr_count", "motion_count"}
        for e in excluded:
            assert e not in features

    def test_includes_numeric_features(self, epochs_df):
        features = get_feature_columns(epochs_df)
        assert "hr_mean" in features
        assert "hrv_mean" in features
        assert "accel_mag_mean" in features
        assert "breathing_rate_mean" in features
        assert "rms_energy_mean" in features

    def test_empty_dataframe(self):
        features = get_feature_columns(pd.DataFrame())
        assert features == []


# =====================================================================
# _slice_by_timestamp() tests
# =====================================================================

class TestSliceByTimestamp:
    """Tests for _slice_by_timestamp()."""

    def test_normal_slice(self):
        df = pd.DataFrame({"timestamp": [0.0, 10.0, 20.0, 30.0], "val": [1, 2, 3, 4]})
        result = _slice_by_timestamp(df, 5.0, 25.0)
        assert len(result) == 2
        assert list(result["val"]) == [2, 3]

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["timestamp", "val"])
        result = _slice_by_timestamp(df, 0.0, 30.0)
        assert result.empty

    def test_no_match(self):
        df = pd.DataFrame({"timestamp": [100.0, 200.0], "val": [1, 2]})
        result = _slice_by_timestamp(df, 0.0, 50.0)
        assert result.empty

    def test_half_open_boundary(self):
        """[start, end) — includes start, excludes end."""
        df = pd.DataFrame({"timestamp": [0.0, 30.0, 60.0], "val": [1, 2, 3]})
        result = _slice_by_timestamp(df, 0.0, 30.0)
        assert len(result) == 1
        assert result.iloc[0]["val"] == 1


# =====================================================================
# _majority_stage() tests
# =====================================================================

class TestMajorityStage:
    """Tests for _majority_stage()."""

    def test_single_overlap(self):
        stages = pd.DataFrame({
            "start": [0.0], "end": [60.0], "stage": ["coreLight"],
        })
        assert _majority_stage(stages, 10.0, 40.0) == "coreLight"

    def test_two_overlaps_longer_wins(self):
        stages = pd.DataFrame({
            "start": [0.0, 20.0], "end": [20.0, 60.0],
            "stage": ["coreLight", "deepSleep"],
        })
        # Epoch [10, 50): coreLight overlap=10, deepSleep overlap=30
        assert _majority_stage(stages, 10.0, 50.0) == "deepSleep"

    def test_empty_stages_returns_none(self):
        stages = pd.DataFrame(columns=["start", "end", "stage"])
        assert _majority_stage(stages, 0.0, 30.0) is None

    def test_no_overlap_returns_none(self):
        stages = pd.DataFrame({
            "start": [100.0], "end": [200.0], "stage": ["remSleep"],
        })
        assert _majority_stage(stages, 0.0, 30.0) is None
