"""Shared test fixtures for inference server tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add inference package to path so tests can import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Add analysis package to path
_analysis_dir = Path(__file__).resolve().parent.parent.parent / "analysis"
sys.path.insert(0, str(_analysis_dir))

MODELS_DIR = Path(__file__).parent.parent / "models"
TEST_JWT_SECRET = "test-secret-key-for-unit-tests"


@pytest.fixture
def model_dir() -> Path:
    """Path to the test model directory. Skip if model not generated."""
    if not (MODELS_DIR / "model.joblib").exists():
        pytest.skip("Test model not generated. Run: python generate_test_model.py")
    return MODELS_DIR


@pytest.fixture
def feature_names(model_dir: Path) -> list[str]:
    """Load feature names from test model."""
    with open(model_dir / "feature_names.json") as f:
        return json.load(f)


@pytest.fixture
def jwt_secret() -> str:
    return TEST_JWT_SECRET


@pytest.fixture
def sample_sensor_epoch() -> dict:
    """A realistic sensor_epoch message payload."""
    return {
        "type": "sensor_epoch",
        "epoch_index": 0,
        "timestamp": "2026-03-16T01:00:00Z",
        "data": {
            "hr_samples": [62.1, 63.0, 61.8, 62.5, 63.2, 61.5],
            "hrv_samples": [48.2],
            "accel_x": [0.01, -0.02, 0.03, 0.01, -0.01],
            "accel_y": [0.98, 0.97, 0.99, 0.98, 0.97],
            "accel_z": [0.05, 0.04, 0.06, 0.05, 0.04],
            "sonar_breathing_rate": 14.2,
            "sonar_amplitude": 0.73,
            "audio_rms": 0.012,
            "audio_zcr": 0.08,
            "audio_spectral_centroid": 420.5,
            "audio_class": "breathing",
        },
    }
