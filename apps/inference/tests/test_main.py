"""Integration tests for the FastAPI WebSocket server."""

from __future__ import annotations

import json
import importlib
import os
import time
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

TEST_SECRET = "test-secret-key"


def make_token(sub: str = "user-1") -> str:
    payload = {"sub": sub, "iss": "lullaby", "iat": int(time.time()), "exp": int(time.time()) + 3600}
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


@pytest.fixture
def app(model_dir, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("MODEL_PATH", str(model_dir))
    monkeypatch.setenv("ENV", "dev")
    # Force reimport so Settings() picks up the env vars
    import main as main_mod
    importlib.reload(main_mod)
    return main_mod.app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "model_loaded" in data


def test_websocket_requires_auth(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws"):
            pass


def test_websocket_rejects_bad_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws", headers={"Authorization": "Bearer invalid.token.here"}):
            pass


def test_websocket_full_session(client, sample_sensor_epoch):
    token = make_token()
    with client.websocket_connect("/ws", headers={"Authorization": f"Bearer {token}"}) as ws:
        ws.send_json({"type": "session_start", "session_id": "test-session-1", "started_at": "2026-03-16T00:30:00Z"})
        ack = ws.receive_json()
        assert ack["type"] == "session_ack"
        assert ack["session_id"] == "test-session-1"
        assert ack["user_id"] == "user-1"

        ws.send_json(sample_sensor_epoch)
        pred = ws.receive_json()
        assert pred["type"] == "prediction"
        assert pred["epoch_index"] == 0
        assert pred["stage"] in ("awake", "remSleep", "coreLight", "deepSleep", "inBed")
        assert 0.0 <= pred["confidence"] <= 1.0
        assert "probabilities" in pred

        ws.send_json({"type": "session_end"})


def test_websocket_prediction_log_saved(client, sample_sensor_epoch, tmp_path, monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    import main as main_mod
    monkeypatch.setattr(main_mod, "LOGS_DIR", tmp_path)

    token = make_token()
    with client.websocket_connect("/ws", headers={"Authorization": f"Bearer {token}"}) as ws:
        ws.send_json({"type": "session_start", "session_id": "log-test", "started_at": "2026-03-16T00:30:00Z"})
        ws.receive_json()
        ws.send_json(sample_sensor_epoch)
        ws.receive_json()
        ws.send_json({"type": "session_end"})

    log_file = tmp_path / "log-test_predictions.json"
    assert log_file.exists()
    with open(log_file) as f:
        data = json.load(f)
    assert data["session_id"] == "log-test"
    assert len(data["predictions"]) == 1
