"""Tests for real-time feature computation engine."""

from __future__ import annotations

import math

import pytest


def test_feature_engine_computes_base_features(sample_sensor_epoch, feature_names):
    from feature_engine import FeatureEngine
    engine = FeatureEngine(feature_names)
    features = engine.compute(sample_sensor_epoch["data"], sample_sensor_epoch["timestamp"])
    assert "hr_mean" in features
    assert 50 < features["hr_mean"] < 100
    assert "hr_std" in features
    assert "hr_min" in features
    assert "hr_max" in features
    assert "hr_range" in features


def test_feature_engine_computes_accel_magnitude(sample_sensor_epoch, feature_names):
    from feature_engine import FeatureEngine
    engine = FeatureEngine(feature_names)
    features = engine.compute(sample_sensor_epoch["data"], sample_sensor_epoch["timestamp"])
    assert "accel_mag_mean" in features
    assert features["accel_mag_mean"] > 0


def test_feature_engine_temporal_features_nan_first_epoch(sample_sensor_epoch, feature_names):
    from feature_engine import FeatureEngine
    engine = FeatureEngine(feature_names)
    features = engine.compute(sample_sensor_epoch["data"], sample_sensor_epoch["timestamp"])
    rolling_keys = [k for k in features if "roll" in k or "delta" in k]
    for key in rolling_keys:
        assert math.isnan(features[key]), f"{key} should be NaN on first epoch"


def test_feature_engine_temporal_features_after_multiple_epochs(sample_sensor_epoch, feature_names):
    from feature_engine import FeatureEngine
    engine = FeatureEngine(feature_names)
    for i in range(5):
        epoch_data = dict(sample_sensor_epoch["data"])
        epoch_data["hr_samples"] = [60.0 + i, 61.0 + i, 62.0 + i]
        features = engine.compute(epoch_data, f"2026-03-16T01:{i:02d}:00Z")
    # breathing_regularity_mean has no sensor source, so its derived rolling
    # features stay NaN — exclude them from the non-NaN assertion.
    always_nan_bases = {"breathing_regularity_mean"}
    roll3_keys = [
        k for k in features if "roll3" in k
        and not any(k.startswith(base) for base in always_nan_bases)
    ]
    for key in roll3_keys:
        assert not math.isnan(features[key]), f"{key} should not be NaN after 5 epochs"


def test_feature_engine_audio_onehot(sample_sensor_epoch, feature_names):
    from feature_engine import FeatureEngine
    engine = FeatureEngine(feature_names)
    features = engine.compute(sample_sensor_epoch["data"], sample_sensor_epoch["timestamp"])
    assert features.get("audio_is_breathing", 0) == 1.0
    assert features.get("audio_is_silence", 0) == 0.0
    assert features.get("audio_is_snoring", 0) == 0.0
    assert features.get("audio_is_movement", 0) == 0.0


def test_feature_engine_time_of_night(feature_names):
    from feature_engine import FeatureEngine
    engine = FeatureEngine(feature_names)
    data = {"hr_samples": [65.0], "hrv_samples": [], "accel_x": [], "accel_y": [], "accel_z": []}
    features = engine.compute(data.copy(), "2026-03-16T00:00:00Z")
    if "time_of_night" in features:
        assert 0.0 <= features["time_of_night"] <= 1.0


def test_feature_engine_returns_all_expected_features(sample_sensor_epoch, feature_names):
    from feature_engine import FeatureEngine
    engine = FeatureEngine(feature_names)
    features = engine.compute(sample_sensor_epoch["data"], sample_sensor_epoch["timestamp"])
    for name in feature_names:
        assert name in features, f"Missing feature: {name}"
