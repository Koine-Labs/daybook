"""Tests for WebSocket message schemas."""

from __future__ import annotations

import pytest


def test_sensor_epoch_valid(sample_sensor_epoch):
    from schemas import SensorEpoch
    msg = SensorEpoch(**sample_sensor_epoch)
    assert msg.type == "sensor_epoch"
    assert msg.epoch_index == 0
    assert len(msg.data.hr_samples) == 6
    assert msg.data.audio_class == "breathing"


def test_sensor_epoch_missing_hr():
    from schemas import SensorEpoch
    with pytest.raises(Exception):
        SensorEpoch(type="sensor_epoch", epoch_index=0, timestamp="2026-03-16T01:00:00Z", data={"accel_x": [0.1]})


def test_session_start_valid():
    from schemas import SessionStart
    msg = SessionStart(type="session_start", session_id="abc-123", started_at="2026-03-16T00:30:00Z")
    assert msg.session_id == "abc-123"


def test_prediction_serialization():
    from schemas import Prediction, StageProbabilities
    pred = Prediction(type="prediction", epoch_index=5, stage="remSleep", confidence=0.82,
        probabilities=StageProbabilities(awake=0.03, coreLight=0.08, deepSleep=0.05, remSleep=0.82, inBed=0.02))
    data = pred.model_dump()
    assert data["stage"] == "remSleep"
    assert data["probabilities"]["remSleep"] == 0.82


def test_session_ack_serialization():
    from schemas import SessionAck
    ack = SessionAck(type="session_ack", session_id="abc", user_id="user-1")
    assert ack.user_id == "user-1"


def test_error_message():
    from schemas import ErrorMessage
    err = ErrorMessage(type="error", message="bad input")
    assert err.message == "bad input"


def test_parse_incoming_message(sample_sensor_epoch):
    from schemas import parse_incoming
    msg = parse_incoming(sample_sensor_epoch)
    assert msg.type == "sensor_epoch"
    start = parse_incoming({"type": "session_start", "session_id": "x", "started_at": "2026-01-01T00:00:00Z"})
    assert start.type == "session_start"
    end = parse_incoming({"type": "session_end"})
    assert end.type == "session_end"


def test_parse_incoming_unknown_type():
    from schemas import parse_incoming
    with pytest.raises(ValueError, match="Unknown message type"):
        parse_incoming({"type": "unknown_thing"})
