"""Tests for lullaby.loader — JSON loading and mock data generation."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lullaby.loader import (
    SleepSessionData,
    generate_mock_session,
    load_session,
    load_all_sessions,
    _parse_iso8601,
    _generate_sleep_architecture,
)


# =====================================================================
# Mock generator tests
# =====================================================================

class TestGenerateMockSession:
    """Tests for generate_mock_session()."""

    def test_returns_sleep_session_data(self):
        session = generate_mock_session(seed=1)
        assert isinstance(session, SleepSessionData)

    def test_deterministic_with_same_seed(self):
        s1 = generate_mock_session(seed=42)
        s2 = generate_mock_session(seed=42)
        pd.testing.assert_frame_equal(s1.heart_rate, s2.heart_rate)
        pd.testing.assert_frame_equal(s1.sleep_stages, s2.sleep_stages)

    def test_different_seeds_differ(self):
        s1 = generate_mock_session(seed=1)
        s2 = generate_mock_session(seed=2)
        assert not s1.heart_rate["bpm"].equals(s2.heart_rate["bpm"])

    def test_duration_accuracy(self):
        session = generate_mock_session(duration_hours=4.0, seed=10)
        assert session.duration_hours == 4.0
        # Sensor data should span roughly the full duration
        max_hr_ts = session.heart_rate["timestamp"].max()
        assert max_hr_ts > (4.0 * 3600 * 0.9)  # At least 90% of duration covered

    def test_hr_physiological_range(self, mock_session):
        """Heart rate should be clipped to [40, 120] BPM."""
        assert mock_session.heart_rate["bpm"].min() >= 40
        assert mock_session.heart_rate["bpm"].max() <= 120

    def test_hrv_physiological_range(self, mock_session):
        """HRV SDNN should be clipped to [10, 150] ms."""
        assert mock_session.hrv["sdnn"].min() >= 10
        assert mock_session.hrv["sdnn"].max() <= 150

    def test_breathing_rate_range(self, mock_session):
        """Breathing rate should be clipped to [8, 30] breaths/min."""
        br = mock_session.sonar["breathing_rate"]
        assert br.min() >= 8
        assert br.max() <= 30

    def test_breathing_regularity_range(self, mock_session):
        """Breathing regularity should be clipped to [0, 1]."""
        reg = mock_session.sonar["breathing_regularity"]
        assert reg.min() >= 0
        assert reg.max() <= 1

    def test_timestamps_sorted(self, mock_session):
        """All sensor DataFrames should have sorted timestamps."""
        for name, df in [
            ("heart_rate", mock_session.heart_rate),
            ("hrv", mock_session.hrv),
            ("accelerometer", mock_session.accelerometer),
            ("sonar", mock_session.sonar),
            ("audio", mock_session.audio),
        ]:
            if not df.empty:
                assert df["timestamp"].is_monotonic_increasing, f"{name} not sorted"

    def test_sleep_architecture_completeness(self, mock_session):
        """Sleep stages should include multiple stage types."""
        stages = set(mock_session.sleep_stages["stage"].unique())
        # Should have at least light, deep, and REM for an 8-hour night
        assert "coreLight" in stages
        assert "deepSleep" in stages
        assert "remSleep" in stages

    def test_short_duration(self):
        """Even very short sessions should not crash."""
        session = generate_mock_session(duration_hours=0.1, seed=5)
        assert session.duration_hours == 0.1
        assert len(session.heart_rate) > 0

    def test_long_duration(self):
        """12-hour session should produce more data than 4-hour."""
        s4 = generate_mock_session(duration_hours=4.0, seed=1)
        s12 = generate_mock_session(duration_hours=12.0, seed=1)
        assert len(s12.heart_rate) > len(s4.heart_rate)

    def test_metadata_populated(self, mock_session):
        """Metadata should have battery and connectivity info."""
        meta = mock_session.metadata
        assert "watchBatteryAtStart" in meta
        assert "watchBatteryAtEnd" in meta
        assert "phoneBatteryAtStart" in meta
        assert "totalPacketsReceived" in meta
        assert "connectivityDropCount" in meta

    def test_no_stage_overlaps(self, mock_session):
        """Sleep stage intervals should not overlap."""
        stages = mock_session.sleep_stages
        for i in range(len(stages) - 1):
            assert stages.iloc[i]["end"] <= stages.iloc[i + 1]["start"] + 0.01, \
                f"Stage overlap at index {i}"


# =====================================================================
# JSON loading tests
# =====================================================================

class TestLoadSession:
    """Tests for load_session()."""

    def test_roundtrip_save_and_load(self, mock_json_path):
        """Save mock as JSON, load it back, verify key fields."""
        session = load_session(mock_json_path)
        assert isinstance(session, SleepSessionData)
        assert session.duration_hours > 0
        assert not session.heart_rate.empty
        assert not session.sleep_stages.empty

    def test_loaded_hr_matches_expected_columns(self, mock_json_path):
        session = load_session(mock_json_path)
        assert list(session.heart_rate.columns) == ["timestamp", "bpm"]

    def test_loaded_sonar_columns(self, mock_json_path):
        session = load_session(mock_json_path)
        expected = ["timestamp", "breathing_rate", "breathing_regularity", "signal_strength"]
        assert list(session.sonar.columns) == expected

    def test_loaded_audio_columns(self, mock_json_path):
        session = load_session(mock_json_path)
        expected = ["timestamp", "dominant_frequency", "spectral_centroid", "rms_energy", "zcr", "classification"]
        assert list(session.audio.columns) == expected

    def test_loaded_sleep_stage_columns(self, mock_json_path):
        session = load_session(mock_json_path)
        assert list(session.sleep_stages.columns) == ["start", "end", "stage"]

    def test_missing_end_date(self, tmp_path):
        """Session with no endDate should have end_time=None, duration=0."""
        data = {
            "id": "test-no-end",
            "startDate": "2025-03-15T23:00:00Z",
            "watchPackets": [],
            "sonarFeatures": [],
            "audioFeatures": [],
            "sleepStages": [],
        }
        path = tmp_path / "no_end.json"
        path.write_text(json.dumps(data))
        session = load_session(path)
        assert session.end_time is None
        assert session.duration_hours == 0.0

    def test_empty_watch_packets(self, tmp_path):
        """No watchPackets → empty HR, HRV, accel DataFrames."""
        data = {
            "id": "test-empty-packets",
            "startDate": "2025-03-15T23:00:00Z",
            "endDate": "2025-03-16T07:00:00Z",
            "watchPackets": [],
            "sonarFeatures": [],
            "audioFeatures": [],
            "sleepStages": [],
        }
        path = tmp_path / "empty.json"
        path.write_text(json.dumps(data))
        session = load_session(path)
        assert session.heart_rate.empty
        assert session.hrv.empty
        assert session.accelerometer.empty

    def test_empty_sonar_features(self, tmp_path):
        data = {
            "id": "test-no-sonar",
            "startDate": "2025-03-15T23:00:00Z",
            "endDate": "2025-03-16T07:00:00Z",
            "watchPackets": [],
            "sonarFeatures": [],
            "audioFeatures": [],
            "sleepStages": [],
        }
        path = tmp_path / "no_sonar.json"
        path.write_text(json.dumps(data))
        session = load_session(path)
        assert session.sonar.empty

    def test_empty_audio_features(self, tmp_path):
        data = {
            "id": "test-no-audio",
            "startDate": "2025-03-15T23:00:00Z",
            "endDate": "2025-03-16T07:00:00Z",
            "watchPackets": [],
            "sonarFeatures": [],
            "audioFeatures": [],
            "sleepStages": [],
        }
        path = tmp_path / "no_audio.json"
        path.write_text(json.dumps(data))
        session = load_session(path)
        assert session.audio.empty

    def test_empty_sleep_stages(self, tmp_path):
        data = {
            "id": "test-no-stages",
            "startDate": "2025-03-15T23:00:00Z",
            "endDate": "2025-03-16T07:00:00Z",
            "watchPackets": [],
            "sonarFeatures": [],
            "audioFeatures": [],
            "sleepStages": [],
        }
        path = tmp_path / "no_stages.json"
        path.write_text(json.dumps(data))
        session = load_session(path)
        assert session.sleep_stages.empty

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("NOT JSON AT ALL{{{")
        with pytest.raises(json.JSONDecodeError):
            load_session(path)

    def test_missing_required_key_raises(self, tmp_path):
        """JSON without 'id' key should raise KeyError."""
        data = {"startDate": "2025-03-15T23:00:00Z"}
        path = tmp_path / "missing_id.json"
        path.write_text(json.dumps(data))
        with pytest.raises(KeyError):
            load_session(path)

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            load_session("/nonexistent/path/no_file.json")

    def test_metadata_loaded(self, mock_json_path):
        session = load_session(mock_json_path)
        assert isinstance(session.metadata, dict)


# =====================================================================
# Batch loading tests
# =====================================================================

class TestLoadAllSessions:
    """Tests for load_all_sessions()."""

    def test_loads_multiple_files_sorted(self, mock_json_dir):
        sessions = load_all_sessions(mock_json_dir)
        assert len(sessions) == 3
        # Should be sorted by start_time
        for i in range(len(sessions) - 1):
            assert sessions[i].start_time <= sessions[i + 1].start_time

    def test_empty_directory(self, tmp_path):
        sessions = load_all_sessions(tmp_path)
        assert sessions == []

    def test_skips_malformed_files(self, tmp_path):
        """Malformed JSONs should be skipped, valid ones loaded."""
        # One valid file
        generate_mock_session(duration_hours=1.0, seed=42, save_json=True,
                              output_path=tmp_path / "good.json")
        # One malformed file
        (tmp_path / "bad.json").write_text("NOT VALID JSON")
        sessions = load_all_sessions(tmp_path)
        assert len(sessions) == 1


# =====================================================================
# Helper function tests
# =====================================================================

class TestParseISO8601:
    """Tests for _parse_iso8601()."""

    def test_z_suffix(self):
        dt = _parse_iso8601("2025-03-15T23:00:00Z")
        assert dt.tzinfo is not None
        assert dt.year == 2025
        assert dt.month == 3
        assert dt.day == 15
        assert dt.hour == 23

    def test_offset_format(self):
        dt = _parse_iso8601("2025-03-15T23:00:00+00:00")
        assert dt.tzinfo is not None
        assert dt.hour == 23

    def test_negative_offset(self):
        dt = _parse_iso8601("2025-03-15T15:00:00-08:00")
        assert dt.hour == 15


class TestGenerateSleepArchitecture:
    """Tests for _generate_sleep_architecture()."""

    def test_has_rem_stages(self):
        rng = np.random.default_rng(42)
        stages = _generate_sleep_architecture(8 * 3600, rng)
        stage_names = {s[2] for s in stages}
        assert "remSleep" in stage_names

    def test_stages_cover_full_duration(self):
        rng = np.random.default_rng(42)
        total = 8 * 3600
        stages = _generate_sleep_architecture(total, rng)
        # Last stage should end near total duration
        last_end = stages[-1][1]
        assert last_end == pytest.approx(total, abs=1.0)

    def test_no_overlaps(self):
        rng = np.random.default_rng(42)
        stages = _generate_sleep_architecture(8 * 3600, rng)
        for i in range(len(stages) - 1):
            assert stages[i][1] <= stages[i + 1][0] + 0.01


class TestSaveAndReloadJson:
    """Test that save_json option produces a valid file."""

    def test_save_json_creates_file(self, tmp_path):
        out = tmp_path / "test_save.json"
        generate_mock_session(duration_hours=1.0, seed=42, save_json=True, output_path=out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert "id" in data
        assert "watchPackets" in data
        assert "sleepStages" in data
