"""Tests for XGBoost classifier wrapper."""

from __future__ import annotations

import logging

import pytest


def test_classifier_loads_model(model_dir):
    from classifier import Classifier
    clf = Classifier(model_dir)
    assert clf.model is not None
    assert len(clf.feature_names) > 0
    assert "hr_mean" in clf.feature_names


def test_classifier_predict(model_dir, feature_names):
    from classifier import Classifier
    clf = Classifier(model_dir)
    features = {name: 0.5 for name in feature_names}
    features["hr_mean"] = 62.0
    features["hrv_mean"] = 45.0
    result = clf.predict(features)
    assert result.stage in ("awake", "remSleep", "coreLight", "deepSleep", "inBed")
    assert 0.0 <= result.confidence <= 1.0
    assert abs(sum(result.probabilities.values()) - 1.0) < 0.01


def test_classifier_handles_nan_features(model_dir, feature_names):
    from classifier import Classifier
    clf = Classifier(model_dir)
    features = {name: float("nan") for name in feature_names}
    features["hr_mean"] = 65.0
    result = clf.predict(features)
    assert result.stage in ("awake", "remSleep", "coreLight", "deepSleep", "inBed")


def test_classifier_warns_on_missing_features(model_dir, feature_names, caplog):
    from classifier import Classifier
    clf = Classifier(model_dir)
    features = {"hr_mean": 62.0}
    with caplog.at_level(logging.WARNING):
        result = clf.predict(features)
    assert result.stage in ("awake", "remSleep", "coreLight", "deepSleep", "inBed")
