"""Tests for per-session prediction tracking."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_tracker_records_predictions():
    from session_tracker import SessionTracker
    tracker = SessionTracker(session_id="sess-1", user_id="user-1", started_at="2026-03-16T00:30:00Z")
    tracker.add_prediction(epoch_index=0, timestamp="2026-03-16T00:30:30Z", stage="coreLight", confidence=0.75, probabilities={"awake": 0.1, "coreLight": 0.75, "deepSleep": 0.05, "remSleep": 0.05, "inBed": 0.05})
    tracker.add_prediction(epoch_index=1, timestamp="2026-03-16T00:31:00Z", stage="coreLight", confidence=0.80, probabilities={"awake": 0.05, "coreLight": 0.80, "deepSleep": 0.05, "remSleep": 0.05, "inBed": 0.05})
    assert tracker.prediction_count == 2


def test_tracker_serializes_to_json():
    from session_tracker import SessionTracker
    tracker = SessionTracker(session_id="sess-1", user_id="user-1", started_at="2026-03-16T00:30:00Z")
    tracker.add_prediction(epoch_index=0, timestamp="2026-03-16T00:30:30Z", stage="remSleep", confidence=0.82, probabilities={"awake": 0.03, "coreLight": 0.08, "deepSleep": 0.05, "remSleep": 0.82, "inBed": 0.02})
    data = tracker.to_dict()
    assert data["session_id"] == "sess-1"
    assert data["user_id"] == "user-1"
    assert len(data["predictions"]) == 1
    assert data["predictions"][0]["stage"] == "remSleep"


def test_tracker_saves_to_disk(tmp_path):
    from session_tracker import SessionTracker
    tracker = SessionTracker(session_id="sess-1", user_id="user-1", started_at="2026-03-16T00:30:00Z")
    tracker.add_prediction(epoch_index=0, timestamp="2026-03-16T00:30:30Z", stage="deepSleep", confidence=0.90, probabilities={"awake": 0.02, "coreLight": 0.03, "deepSleep": 0.90, "remSleep": 0.03, "inBed": 0.02})
    path = tracker.save_local(tmp_path)
    assert path.exists()
    with open(path) as f:
        saved = json.load(f)
    assert saved["session_id"] == "sess-1"
    assert len(saved["predictions"]) == 1
