"""Tests for the classification data pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lullaby.loader import generate_mock_session
from lullaby.pipeline import (
    ClassificationDataset,
    TrainTestSplit,
    STAGE_LABELS,
    STAGE_TO_INT,
    INT_TO_STAGE,
    prepare_sessions,
    split_by_session,
    get_leave_one_out_splits,
    make_binary_labels,
    generate_mock_dataset,
)


class TestLabelEncoding:
    """Tests for label constants."""

    def test_stage_labels_length(self):
        assert len(STAGE_LABELS) == 5

    def test_stage_to_int_round_trip(self):
        for stage in STAGE_LABELS:
            assert INT_TO_STAGE[STAGE_TO_INT[stage]] == stage

    def test_all_stages_have_mapping(self):
        expected = {"awake", "remSleep", "coreLight", "deepSleep", "inBed"}
        assert set(STAGE_LABELS) == expected


class TestPrepareSessions:
    """Tests for prepare_sessions()."""

    def test_returns_dataset(self):
        sessions = [generate_mock_session(duration_hours=2.0, seed=i) for i in range(3)]
        ds = prepare_sessions(sessions, min_coverage_pct=0.0)
        assert isinstance(ds, ClassificationDataset)

    def test_x_y_shape_match(self):
        sessions = [generate_mock_session(duration_hours=2.0, seed=i) for i in range(2)]
        ds = prepare_sessions(sessions, min_coverage_pct=0.0)
        assert ds.X.shape[0] == ds.y.shape[0]
        assert ds.X.shape[1] == len(ds.feature_names)

    def test_labels_are_valid_ints(self):
        sessions = [generate_mock_session(duration_hours=2.0, seed=42)]
        ds = prepare_sessions(sessions, min_coverage_pct=0.0)
        assert set(ds.y).issubset(set(STAGE_TO_INT.values()))

    def test_session_ids_tracked(self):
        sessions = [generate_mock_session(duration_hours=2.0, seed=i) for i in range(3)]
        ds = prepare_sessions(sessions, min_coverage_pct=0.0)
        unique_ids = np.unique(ds.session_ids)
        assert len(unique_ids) == 3

    def test_quality_gate_filters(self):
        """Sessions below HR coverage threshold should be excluded."""
        sessions = [generate_mock_session(duration_hours=2.0, seed=42)]
        # Mock sessions have high coverage; use impossibly high threshold
        with pytest.raises(ValueError, match="No sessions"):
            prepare_sessions(sessions, min_coverage_pct=999.0)

    def test_no_nan_in_features(self):
        sessions = [generate_mock_session(duration_hours=2.0, seed=42)]
        ds = prepare_sessions(sessions, min_coverage_pct=0.0)
        assert not np.isnan(ds.X).any()

    def test_includes_temporal_features(self):
        sessions = [generate_mock_session(duration_hours=2.0, seed=42)]
        ds = prepare_sessions(sessions, min_coverage_pct=0.0)
        temporal_features = [f for f in ds.feature_names if "roll" in f or "delta" in f or "time_of_night" in f]
        assert len(temporal_features) > 0


class TestSplitBySession:
    """Tests for split_by_session()."""

    def test_returns_train_test_split(self, mock_dataset):
        split = split_by_session(mock_dataset)
        assert isinstance(split, TrainTestSplit)

    def test_no_session_overlap(self, mock_dataset):
        split = split_by_session(mock_dataset)
        train_sessions = set(split.train_session_ids)
        test_sessions = set(split.test_session_ids)
        assert train_sessions.isdisjoint(test_sessions)

    def test_all_sessions_covered(self, mock_dataset):
        split = split_by_session(mock_dataset)
        all_sessions = set(split.train_session_ids) | set(split.test_session_ids)
        assert all_sessions == set(np.unique(mock_dataset.session_ids))

    def test_deterministic(self, mock_dataset):
        split1 = split_by_session(mock_dataset, seed=42)
        split2 = split_by_session(mock_dataset, seed=42)
        assert split1.test_session_ids == split2.test_session_ids

    def test_at_least_one_test_session(self, small_dataset):
        split = split_by_session(small_dataset, test_fraction=0.5)
        assert len(split.test_session_ids) >= 1


class TestGetLeaveOneOutSplits:
    """Tests for get_leave_one_out_splits()."""

    def test_returns_correct_count(self, small_dataset):
        splits = get_leave_one_out_splits(small_dataset)
        n_sessions = len(np.unique(small_dataset.session_ids))
        assert len(splits) == n_sessions

    def test_each_split_holds_one_out(self, small_dataset):
        splits = get_leave_one_out_splits(small_dataset)
        for split in splits:
            assert len(split.test_session_ids) == 1

    def test_test_sets_cover_all_sessions(self, small_dataset):
        splits = get_leave_one_out_splits(small_dataset)
        test_sessions = {s.test_session_ids[0] for s in splits}
        assert test_sessions == set(np.unique(small_dataset.session_ids))


class TestMakeBinaryLabels:
    """Tests for make_binary_labels()."""

    def test_binary_values(self):
        y = np.array([0, 1, 2, 3, 4])  # awake, REM, core, deep, inBed
        binary = make_binary_labels(y)
        assert set(binary).issubset({0, 1})

    def test_rem_is_positive(self):
        rem_int = STAGE_TO_INT["remSleep"]
        y = np.array([rem_int, 0, rem_int, 3])
        binary = make_binary_labels(y)
        assert binary[0] == 1
        assert binary[1] == 0
        assert binary[2] == 1

    def test_preserves_length(self):
        y = np.zeros(100, dtype=np.int64)
        binary = make_binary_labels(y)
        assert len(binary) == 100


class TestGenerateMockDataset:
    """Tests for generate_mock_dataset()."""

    def test_returns_dataset(self):
        ds = generate_mock_dataset(n_sessions=2, duration_hours=1.0, base_seed=42)
        assert isinstance(ds, ClassificationDataset)

    def test_session_count(self):
        ds = generate_mock_dataset(n_sessions=5, duration_hours=1.0, base_seed=42)
        assert len(np.unique(ds.session_ids)) == 5

    def test_has_rem_epochs(self):
        ds = generate_mock_dataset(n_sessions=3, duration_hours=4.0, base_seed=42)
        rem_int = STAGE_TO_INT["remSleep"]
        assert (ds.y == rem_int).sum() > 0
