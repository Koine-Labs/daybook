"""Tests for lullaby.quality — data quality assessment."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lullaby.quality import (
    assess_quality,
    print_quality_report,
    _stream_quality,
    _pct,
)


# =====================================================================
# assess_quality() tests
# =====================================================================

class TestAssessQuality:
    """Tests for assess_quality()."""

    def test_returns_dict_with_expected_keys(self, mock_session):
        report = assess_quality(mock_session)
        expected_keys = {
            "overview", "heart_rate", "hrv", "accelerometer",
            "sonar", "audio", "sleep_stages", "connectivity", "battery",
        }
        assert set(report.keys()) == expected_keys

    def test_overview_fields_present(self, mock_session):
        report = assess_quality(mock_session)
        ov = report["overview"]
        assert "session_id" in ov
        assert "duration_hours" in ov
        assert "start_time" in ov
        assert "end_time" in ov

    def test_hr_coverage_in_range(self, mock_session):
        report = assess_quality(mock_session)
        coverage = report["heart_rate"]["coverage_pct"]
        assert 0 <= coverage <= 200  # Can exceed 100 if data is denser than expected

    def test_gap_detection(self, mock_session):
        report = assess_quality(mock_session)
        hr = report["heart_rate"]
        assert "max_gap_seconds" in hr
        assert hr["max_gap_seconds"] >= 0

    def test_empty_session_all_zeros(self, empty_session):
        report = assess_quality(empty_session)
        assert report["heart_rate"]["actual_count"] == 0
        assert report["hrv"]["actual_count"] == 0
        assert report["accelerometer"]["actual_count"] == 0
        assert report["sonar"]["actual_count"] == 0
        assert report["audio"]["actual_count"] == 0

    def test_zero_duration_no_division_error(self, zero_duration_session):
        """Zero duration should not cause division by zero."""
        report = assess_quality(zero_duration_session)
        assert report["overview"]["duration_hours"] == 0.0
        # Sleep stages with zero duration
        assert report["sleep_stages"]["count"] == 0

    def test_single_sample_handled(self, single_sample_session):
        report = assess_quality(single_sample_session)
        assert report["heart_rate"]["actual_count"] == 1

    def test_sleep_stages_present(self, mock_session):
        report = assess_quality(mock_session)
        ss = report["sleep_stages"]
        assert ss["count"] > 0
        assert ss["coverage_pct"] > 0
        assert "stage_hours" in ss

    def test_sleep_stages_absent(self, empty_session):
        report = assess_quality(empty_session)
        ss = report["sleep_stages"]
        assert ss["count"] == 0
        assert "warning" in ss

    def test_connectivity_fields(self, mock_session):
        report = assess_quality(mock_session)
        conn = report["connectivity"]
        assert "packets_received" in conn
        assert "drop_count" in conn

    def test_battery_drain(self, mock_session):
        report = assess_quality(mock_session)
        bat = report["battery"]
        # Mock metadata has battery fields
        if bat.get("watch_drain_pct") is not None:
            assert bat["watch_drain_pct"] > 0  # Battery should drain

    def test_missing_metadata_defaults(self, empty_session):
        """Empty metadata should not crash, should use defaults."""
        report = assess_quality(empty_session)
        conn = report["connectivity"]
        assert conn["packets_received"] == 0
        assert conn["drop_count"] == 0

    def test_sonar_breathing_rate_stats(self, mock_session):
        report = assess_quality(mock_session)
        sonar = report["sonar"]
        assert "valid_breathing_rate_count" in sonar
        assert "valid_breathing_rate_pct" in sonar

    def test_audio_classification_distribution(self, mock_session):
        report = assess_quality(mock_session)
        audio = report["audio"]
        assert "classification_distribution" in audio
        dist = audio["classification_distribution"]
        assert isinstance(dist, dict)
        assert sum(dist.values()) == report["audio"]["actual_count"]


# =====================================================================
# print_quality_report() tests
# =====================================================================

class TestPrintQualityReport:
    """Tests for print_quality_report()."""

    def test_no_crash_on_mock(self, mock_session, capsys):
        print_quality_report(mock_session)
        captured = capsys.readouterr()
        assert "LULLABY DATA QUALITY REPORT" in captured.out

    def test_no_crash_on_empty(self, empty_session, capsys):
        print_quality_report(empty_session)
        captured = capsys.readouterr()
        assert "LULLABY DATA QUALITY REPORT" in captured.out


# =====================================================================
# Helper function tests
# =====================================================================

class TestStreamQuality:
    """Tests for _stream_quality()."""

    def test_two_samples(self):
        df = pd.DataFrame({"timestamp": [0.0, 5.0], "val": [1, 2]})
        result = _stream_quality(df, "timestamp", 10, "Test", 5.0)
        assert result["actual_count"] == 2
        assert result["mean_interval"] == 5.0

    def test_one_sample(self):
        df = pd.DataFrame({"timestamp": [0.0], "val": [1]})
        result = _stream_quality(df, "timestamp", 10, "Test", 5.0)
        assert result["actual_count"] == 1
        assert result["mean_interval"] == 0

    def test_empty_stream(self):
        df = pd.DataFrame(columns=["timestamp", "val"])
        result = _stream_quality(df, "timestamp", 10, "Test", 5.0)
        assert result["actual_count"] == 0
        assert result["coverage_pct"] == 0

    def test_zero_expected(self):
        df = pd.DataFrame(columns=["timestamp", "val"])
        result = _stream_quality(df, "timestamp", 0, "Test", 5.0)
        assert result["coverage_pct"] == 0


class TestPct:
    """Tests for _pct()."""

    def test_normal_value(self):
        assert _pct(0.85) == "85%"

    def test_none_returns_question_mark(self):
        assert _pct(None) == "?"

    def test_zero(self):
        assert _pct(0.0) == "0%"

    def test_full(self):
        assert _pct(1.0) == "100%"
