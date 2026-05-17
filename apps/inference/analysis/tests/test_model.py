"""Tests for XGBoost model training."""

from __future__ import annotations

import numpy as np
import pytest
from xgboost import XGBClassifier

from lullaby.pipeline import (
    ClassificationDataset,
    STAGE_TO_INT,
    make_binary_labels,
    generate_mock_dataset,
)
from lullaby.model import (
    XGBConfig,
    TrainedModel,
    CVResult,
    DEFAULT_CONFIG,
    train_multiclass,
    train_binary_rem,
    cross_validate,
    tune_hyperparameters,
)


class TestXGBConfig:
    """Tests for XGBConfig."""

    def test_defaults(self):
        config = XGBConfig()
        assert config.n_estimators == 300
        assert config.max_depth == 6
        assert config.learning_rate == 0.1

    def test_frozen(self):
        config = XGBConfig()
        with pytest.raises(AttributeError):
            config.n_estimators = 500

    def test_custom_values(self):
        config = XGBConfig(n_estimators=100, max_depth=3)
        assert config.n_estimators == 100
        assert config.max_depth == 3


class TestTrainMulticlass:
    """Tests for train_multiclass()."""

    def test_returns_trained_model(self, small_dataset):
        model = train_multiclass(small_dataset)
        assert isinstance(model, TrainedModel)
        assert isinstance(model.model, XGBClassifier)
        assert model.binary is False

    def test_can_predict(self, small_dataset):
        model = train_multiclass(small_dataset)
        preds = model.model.predict(small_dataset.X)
        assert len(preds) == len(small_dataset.y)

    def test_predictions_are_valid_classes(self, small_dataset):
        model = train_multiclass(small_dataset)
        preds = model.model.predict(small_dataset.X)
        valid_classes = set(STAGE_TO_INT.values())
        assert set(preds).issubset(valid_classes)

    def test_feature_names_stored(self, small_dataset):
        model = train_multiclass(small_dataset)
        assert model.feature_names == small_dataset.feature_names

    def test_custom_config(self, small_dataset):
        config = XGBConfig(n_estimators=50, max_depth=3)
        model = train_multiclass(small_dataset, config=config)
        assert model.config.n_estimators == 50

    def test_label_map_complete(self, small_dataset):
        model = train_multiclass(small_dataset)
        for i in range(5):
            assert i in model.label_map


class TestTrainBinaryRem:
    """Tests for train_binary_rem()."""

    def test_returns_binary_model(self, small_dataset):
        model = train_binary_rem(small_dataset)
        assert isinstance(model, TrainedModel)
        assert model.binary is True

    def test_binary_predictions(self, small_dataset):
        model = train_binary_rem(small_dataset)
        preds = model.model.predict(small_dataset.X)
        assert set(preds).issubset({0, 1})

    def test_label_map_has_two_classes(self, small_dataset):
        model = train_binary_rem(small_dataset)
        assert len(model.label_map) == 2
        assert "REM" in model.label_map.values()
        assert "non-REM" in model.label_map.values()


class TestCrossValidate:
    """Tests for cross_validate()."""

    def test_returns_cv_result(self, small_dataset):
        result = cross_validate(small_dataset, config=XGBConfig(n_estimators=20))
        assert isinstance(result, CVResult)

    def test_fold_count_matches_sessions(self, small_dataset):
        result = cross_validate(small_dataset, config=XGBConfig(n_estimators=20))
        n_sessions = len(np.unique(small_dataset.session_ids))
        assert len(result.fold_metrics) == n_sessions

    def test_mean_metrics_present(self, small_dataset):
        result = cross_validate(small_dataset, config=XGBConfig(n_estimators=20))
        assert "accuracy" in result.mean_metrics
        assert "rem_f1" in result.mean_metrics

    def test_binary_cv(self, small_dataset):
        result = cross_validate(small_dataset, config=XGBConfig(n_estimators=20), binary=True)
        assert all(m.binary for m in result.fold_models)

    def test_best_fold_index_valid(self, small_dataset):
        result = cross_validate(small_dataset, config=XGBConfig(n_estimators=20))
        assert 0 <= result.best_fold_index < len(result.fold_metrics)

    def test_metrics_in_valid_range(self, small_dataset):
        result = cross_validate(small_dataset, config=XGBConfig(n_estimators=20))
        for m in result.fold_metrics:
            assert 0 <= m["accuracy"] <= 1
            assert 0 <= m["rem_f1"] <= 1


class TestTuneHyperparameters:
    """Tests for tune_hyperparameters()."""

    @pytest.mark.slow
    def test_returns_best_config(self, small_dataset):
        config, result = tune_hyperparameters(
            small_dataset, n_iter=2, seed=42
        )
        assert isinstance(config, XGBConfig)
        assert isinstance(result, CVResult)

    @pytest.mark.slow
    def test_binary_tuning(self, small_dataset):
        config, result = tune_hyperparameters(
            small_dataset, n_iter=2, binary=True, seed=42
        )
        assert all(m.binary for m in result.fold_models)
