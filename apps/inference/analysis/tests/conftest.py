"""Shared fixtures for the Lullaby test suite."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for CI / headless
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from lullaby.loader import SleepSessionData, generate_mock_session
from lullaby.features import align_to_epochs
from lullaby.temporal_features import add_temporal_features
from lullaby.pipeline import prepare_sessions, generate_mock_dataset


# ---------------------------------------------------------------------------
# Auto-use: close all matplotlib figures after every test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _close_figures():
    """Close all matplotlib figures after every test to free memory."""
    yield
    plt.close("all")


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mock_session() -> SleepSessionData:
    """Full 8-hour synthetic sleep session (deterministic, seed=42)."""
    return generate_mock_session(duration_hours=8.0, seed=42)


@pytest.fixture
def short_session() -> SleepSessionData:
    """Short 1-hour session for fast tests."""
    return generate_mock_session(duration_hours=1.0, seed=99)


@pytest.fixture
def empty_session() -> SleepSessionData:
    """Session with all DataFrames empty (correct columns, 0 rows)."""
    return SleepSessionData(
        session_id="empty-session",
        start_time=pd.Timestamp("2025-03-15 23:00:00", tz="UTC").to_pydatetime(),
        end_time=pd.Timestamp("2025-03-16 07:00:00", tz="UTC").to_pydatetime(),
        duration_hours=8.0,
        heart_rate=pd.DataFrame(columns=["timestamp", "bpm"]),
        hrv=pd.DataFrame(columns=["timestamp", "sdnn"]),
        accelerometer=pd.DataFrame(columns=["timestamp", "x", "y", "z"]),
        sonar=pd.DataFrame(columns=["timestamp", "breathing_rate", "breathing_regularity", "signal_strength"]),
        audio=pd.DataFrame(columns=["timestamp", "dominant_frequency", "spectral_centroid", "rms_energy", "zcr", "classification"]),
        sleep_stages=pd.DataFrame(columns=["start", "end", "stage"]),
        metadata={},
    )


@pytest.fixture
def single_sample_session() -> SleepSessionData:
    """Session where every DataFrame has exactly 1 row."""
    return SleepSessionData(
        session_id="single-sample",
        start_time=pd.Timestamp("2025-03-15 23:00:00", tz="UTC").to_pydatetime(),
        end_time=pd.Timestamp("2025-03-15 23:00:30", tz="UTC").to_pydatetime(),
        duration_hours=30 / 3600,
        heart_rate=pd.DataFrame({"timestamp": [15.0], "bpm": [72.0]}),
        hrv=pd.DataFrame({"timestamp": [15.0], "sdnn": [45.0]}),
        accelerometer=pd.DataFrame({"timestamp": [15.0], "x": [0.01], "y": [0.02], "z": [1.0]}),
        sonar=pd.DataFrame({"timestamp": [15.0], "breathing_rate": [16.0], "breathing_regularity": [0.7], "signal_strength": [-35.0]}),
        audio=pd.DataFrame({"timestamp": [15.0], "dominant_frequency": [500.0], "spectral_centroid": [1500.0], "rms_energy": [-30.0], "zcr": [0.05], "classification": ["breathing"]}),
        sleep_stages=pd.DataFrame({"start": [0.0], "end": [30.0], "stage": ["coreLight"]}),
        metadata={},
    )


@pytest.fixture
def no_rem_session() -> SleepSessionData:
    """Session with sleep stages but no REM at all."""
    return SleepSessionData(
        session_id="no-rem-session",
        start_time=pd.Timestamp("2025-03-15 23:00:00", tz="UTC").to_pydatetime(),
        end_time=pd.Timestamp("2025-03-16 01:00:00", tz="UTC").to_pydatetime(),
        duration_hours=2.0,
        heart_rate=pd.DataFrame({"timestamp": np.arange(0, 7200, 5, dtype=float), "bpm": np.random.default_rng(1).normal(65, 5, 1440)}),
        hrv=pd.DataFrame({"timestamp": np.arange(0, 7200, 300, dtype=float), "sdnn": np.random.default_rng(1).normal(50, 10, 24)}),
        accelerometer=pd.DataFrame({"timestamp": [0.0, 3600.0], "x": [0.0, 0.0], "y": [0.0, 0.0], "z": [1.0, 1.0]}),
        sonar=pd.DataFrame({"timestamp": np.arange(0, 7200, 2, dtype=float), "breathing_rate": np.random.default_rng(1).normal(15, 2, 3600), "breathing_regularity": np.random.default_rng(1).uniform(0.5, 0.9, 3600), "signal_strength": np.random.default_rng(1).normal(-35, 5, 3600)}),
        audio=pd.DataFrame({"timestamp": np.arange(0, 7200, 5, dtype=float), "dominant_frequency": np.random.default_rng(1).normal(500, 200, 1440), "spectral_centroid": np.random.default_rng(1).normal(1500, 500, 1440), "rms_energy": np.random.default_rng(1).normal(-30, 5, 1440), "zcr": np.random.default_rng(1).uniform(0, 0.1, 1440), "classification": np.random.default_rng(1).choice(["silence", "breathing", "ambientNoise"], 1440)}),
        sleep_stages=pd.DataFrame({
            "start": [0.0, 1800.0, 3600.0, 5400.0],
            "end": [1800.0, 3600.0, 5400.0, 7200.0],
            "stage": ["coreLight", "deepSleep", "coreLight", "deepSleep"],
        }),
        metadata={},
    )


@pytest.fixture
def zero_duration_session() -> SleepSessionData:
    """Session with duration_hours=0."""
    return SleepSessionData(
        session_id="zero-duration",
        start_time=pd.Timestamp("2025-03-15 23:00:00", tz="UTC").to_pydatetime(),
        end_time=None,
        duration_hours=0.0,
        heart_rate=pd.DataFrame(columns=["timestamp", "bpm"]),
        hrv=pd.DataFrame(columns=["timestamp", "sdnn"]),
        accelerometer=pd.DataFrame(columns=["timestamp", "x", "y", "z"]),
        sonar=pd.DataFrame(columns=["timestamp", "breathing_rate", "breathing_regularity", "signal_strength"]),
        audio=pd.DataFrame(columns=["timestamp", "dominant_frequency", "spectral_centroid", "rms_energy", "zcr", "classification"]),
        sleep_stages=pd.DataFrame(columns=["start", "end", "stage"]),
        metadata={},
    )


# ---------------------------------------------------------------------------
# JSON file fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_json_path(tmp_path) -> Path:
    """Write a mock session as JSON to a temp file and return its path."""
    generate_mock_session(duration_hours=2.0, seed=42, save_json=True,
                          output_path=tmp_path / "session.json")
    return tmp_path / "session.json"


@pytest.fixture
def mock_json_dir(tmp_path) -> Path:
    """Directory with 3 mock JSON session files."""
    for i, seed in enumerate([10, 20, 30]):
        generate_mock_session(
            duration_hours=1.0,
            seed=seed,
            save_json=True,
            output_path=tmp_path / f"session_{i}.json",
        )
    return tmp_path


# ---------------------------------------------------------------------------
# Derived data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def epochs_df(mock_session) -> pd.DataFrame:
    """Pre-computed 30-second epoch DataFrame from the full mock session."""
    return align_to_epochs(mock_session)


# ---------------------------------------------------------------------------
# Phase 2 fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def temporal_epochs_df(epochs_df) -> pd.DataFrame:
    """Epoch DataFrame with temporal features added."""
    return add_temporal_features(epochs_df)


@pytest.fixture(scope="session")
def mock_dataset():
    """10-session mock classification dataset."""
    return generate_mock_dataset(n_sessions=10, duration_hours=2.0, base_seed=100)


@pytest.fixture(scope="session")
def small_dataset():
    """2-session mock classification dataset for fast tests."""
    return generate_mock_dataset(n_sessions=2, duration_hours=2.0, base_seed=200)
