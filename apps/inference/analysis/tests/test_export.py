"""Tests for model serialization and export."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from lullaby.pipeline import generate_mock_dataset
from lullaby.model import XGBConfig, train_multiclass, train_binary_rem
from lullaby.evaluation import compute_metrics, ClassificationMetrics
from lullaby.export import save_model, load_model, export_coreml, ModelArtifact


class TestSaveModel:
    """Tests for save_model()."""

    def test_creates_files(self, tmp_path, small_dataset):
        model = train_multiclass(small_dataset, config=XGBConfig(n_estimators=20))
        output = save_model(model, tmp_path / "model_v1")
        assert (output / "model.joblib").exists()
        assert (output / "config.json").exists()
        assert (output / "feature_names.json").exists()

    def test_config_json_valid(self, tmp_path, small_dataset):
        model = train_multiclass(small_dataset, config=XGBConfig(n_estimators=20))
        output = save_model(model, tmp_path / "model_v1", version="1.0.0")
        with open(output / "config.json") as f:
            config = json.load(f)
        assert config["version"] == "1.0.0"
        assert config["binary"] is False
        assert "hyperparameters" in config

    def test_feature_names_match(self, tmp_path, small_dataset):
        model = train_multiclass(small_dataset, config=XGBConfig(n_estimators=20))
        output = save_model(model, tmp_path / "model_v1")
        with open(output / "feature_names.json") as f:
            names = json.load(f)
        assert names == model.feature_names

    def test_with_metrics(self, tmp_path, small_dataset):
        model = train_multiclass(small_dataset, config=XGBConfig(n_estimators=20))
        preds = model.model.predict(small_dataset.X)
        metrics = compute_metrics(small_dataset.y, preds)
        output = save_model(model, tmp_path / "model_v1", metrics=metrics)
        with open(output / "config.json") as f:
            config = json.load(f)
        assert "metrics" in config
        assert "rem_f1" in config["metrics"]


class TestLoadModel:
    """Tests for load_model()."""

    def test_roundtrip(self, tmp_path, small_dataset):
        model = train_multiclass(small_dataset, config=XGBConfig(n_estimators=20))
        save_model(model, tmp_path / "model_v1")
        loaded, artifact = load_model(tmp_path / "model_v1")
        assert loaded.feature_names == model.feature_names
        assert loaded.binary == model.binary
        assert loaded.config.n_estimators == model.config.n_estimators

    def test_loaded_model_can_predict(self, tmp_path, small_dataset):
        model = train_multiclass(small_dataset, config=XGBConfig(n_estimators=20))
        save_model(model, tmp_path / "model_v1")
        loaded, _ = load_model(tmp_path / "model_v1")
        preds = loaded.model.predict(small_dataset.X)
        assert len(preds) == len(small_dataset.y)

    def test_missing_directory(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_model(tmp_path / "nonexistent")

    def test_binary_roundtrip(self, tmp_path, small_dataset):
        model = train_binary_rem(small_dataset, config=XGBConfig(n_estimators=20))
        save_model(model, tmp_path / "binary_v1")
        loaded, _ = load_model(tmp_path / "binary_v1")
        assert loaded.binary is True


class TestExportCoreml:
    """Tests for export_coreml()."""

    @pytest.mark.slow
    def test_creates_mlmodel(self, tmp_path, small_dataset):
        model = train_multiclass(small_dataset, config=XGBConfig(n_estimators=20))
        output = export_coreml(model, tmp_path / "model.mlmodel")
        assert output.exists()
        assert output.suffix == ".mlmodel"
