# apps/inference/prediction/test_prediction_log.py
"""DB-free tests for the L4 PredictionLogWriter (fake conns, no psycopg)."""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.bus.bus import TOPIC_BELIEF, TOPIC_FEATURE, TOPIC_PREDICTION, MessageBus  # noqa: E402
from core.protocol.enums import MetaContext, Modality, NodeRole, PayloadType  # noqa: E402
from core.protocol.envelope import MessageEnvelope  # noqa: E402
from core.protocol.payloads import Prediction  # noqa: E402
from features.snapshot import FeatureSnapshot  # noqa: E402
from fusion.belief_state import AxisEstimate, BeliefState  # noqa: E402
from prediction import feature_participant as l4f  # noqa: E402
from prediction import participant as l4  # noqa: E402
from prediction.interface import make_offline  # noqa: E402
from prediction.prediction_log import (  # noqa: E402
    ACTION_CONDITIONING_NAIVE,
    ACTION_CONDITIONING_NONE,
    PredictionLogWriter,
    estimate_inputs,
    feature_inputs,
)

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
IMODEL = "im-pred-001"

INSERT_COLUMNS = (
    "user_id", "axis", "meta_context", "made_at", "horizon_seconds",
    "prediction", "action_conditioned_on", "model_id", "inputs_used",
    "cold_start", "action_conditioning_kind", "i_model_id",
)


class _FakeCursor:
    def __init__(self, store: list) -> None:
        self._store = store

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self._store.append((sql, params))

    def fetchone(self) -> tuple:
        return (str(uuid.uuid4()),)

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_a: object) -> bool:
        return False


class _FakeConn:
    def __init__(self, store: list) -> None:
        self._store = store
        self.committed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._store)

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *_a: object) -> bool:
        return False


def _prediction(
    *,
    axis: str = "meta_context",
    action: dict[str, Any] | None = None,
    distribution: dict[str, Any] | None = None,
) -> Prediction:
    return Prediction(
        user_id=USER,
        axis=axis,
        made_at=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        horizon_seconds=300,
        distribution=distribution or {"kind": "persistence", "informative": False},
        model_id="prediction.stub.persistence.v0",
        confidence=0.7,
        action=action,
        provenance="placeholder",
        cold_start=True,
        i_model_id=IMODEL,
    )


def test_write_inserts_exact_columns_and_values():
    store: list = []
    conn = _FakeConn(store)
    writer = PredictionLogWriter(conn_factory=lambda: conn)
    pred = _prediction()
    inputs = {"kind": "axis_estimate", "axis": "meta_context"}

    new_id = writer.write(pred, meta_context="waking", inputs_used=inputs)

    assert new_id is not None
    assert conn.committed is True
    sql, params = store[0]
    assert "INSERT INTO prediction_log" in sql
    for col in INSERT_COLUMNS:
        assert col in sql
    assert params[0] == USER
    assert params[1] == "meta_context"
    assert params[2] == "waking"
    assert params[3] == pred.made_at
    assert params[4] == 300
    assert json.loads(params[5]) == {
        "distribution": pred.distribution,
        "confidence": 0.7,
        "provenance": "placeholder",
    }
    assert params[6] is None
    assert params[7] == "prediction.stub.persistence.v0"
    assert json.loads(params[8]) == inputs
    assert params[9] is True
    assert params[10] == ACTION_CONDITIONING_NONE
    assert params[11] == IMODEL


def test_action_conditioned_prediction_round_trips_action_json():
    store: list = []
    writer = PredictionLogWriter(conn_factory=lambda: _FakeConn(store))
    pred = _prediction(action={"kind": "interject", "mode": "companion"})

    writer.write(pred, meta_context="waking")

    _sql, params = store[0]
    assert json.loads(params[6]) == {"kind": "interject", "mode": "companion"}
    assert params[10] == ACTION_CONDITIONING_NAIVE


def test_offline_prediction_is_not_logged():
    store: list = []
    conn = _FakeConn(store)
    writer = PredictionLogWriter(conn_factory=lambda: conn)
    offline = make_offline(user_id=USER, axis="valence", horizon_seconds=300)

    assert writer.write(offline, meta_context="waking") is None
    assert store == []
    assert conn.committed is False


def test_write_returns_none_when_db_absent():
    def _boom() -> _FakeConn:
        raise RuntimeError("DATABASE_URL not set")

    writer = PredictionLogWriter(conn_factory=_boom)
    assert writer.write(_prediction(), meta_context="waking") is None


def test_non_finite_floats_sanitize_to_null():
    store: list = []
    writer = PredictionLogWriter(conn_factory=lambda: _FakeConn(store))
    pred = _prediction(distribution={"prob": float("nan")})

    writer.write(pred, inputs_used={"features": {"hr_mean": float("inf")}})

    _sql, params = store[0]
    assert json.loads(params[5])["distribution"] == {"prob": None}
    assert json.loads(params[8]) == {"features": {"hr_mean": None}}


def test_estimate_inputs_packs_axis_estimate():
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    est = AxisEstimate(
        axis="meta_context",
        value={"category": "waking/focused"},
        timestamp=now,
        confidence=0.8,
        source="L3.fusion.meta_context",
    )
    assert estimate_inputs(est) == {
        "kind": "axis_estimate",
        "axis": "meta_context",
        "value": {"category": "waking/focused"},
        "timestamp": now.isoformat(),
        "confidence": 0.8,
        "source": "L3.fusion.meta_context",
    }
    assert estimate_inputs(None) is None


def test_feature_inputs_packs_features():
    assert feature_inputs({"hr_mean": 66.0}) == {
        "kind": "feature_snapshot",
        "features": {"hr_mean": 66.0},
    }


# --- participant wiring -------------------------------------------------------

def _belief_envelope(*, with_unregistered: bool = False) -> MessageEnvelope:
    now = datetime.now(timezone.utc)
    bs = BeliefState(user_id=USER)
    bs.update(
        AxisEstimate(
            axis="meta_context",
            value={"category": "waking/focused"},
            timestamp=now,
            confidence=0.8,
            source="L3.fusion.meta_context",
        )
    )
    if with_unregistered:
        bs.update(
            AxisEstimate(
                axis="valence",
                value={"label": "neutral"},
                timestamp=now,
                confidence=0.5,
                source="L3.fusion.valence",
            )
        )
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.BELIEF,
        source_role=NodeRole.DESKTOP_COMPUTE,
        occurred_at=now,
        meta_context=MetaContext.WAKING,
        consent_scope="mic_continuous_v1",
        trace_id=str(uuid.uuid4()),
        payload=bs,
        i_model_id=IMODEL,
    )


def test_participant_without_writer_is_unchanged():
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_PREDICTION, captured.append)
    l4.register(bus)

    bus.publish(TOPIC_BELIEF, _belief_envelope(with_unregistered=True))

    assert len(captured) == 2


def test_participant_with_writer_logs_non_offline_only():
    store: list = []
    writer = PredictionLogWriter(conn_factory=lambda: _FakeConn(store))
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_PREDICTION, captured.append)
    l4.register(bus, writer=writer)

    bus.publish(TOPIC_BELIEF, _belief_envelope(with_unregistered=True))

    assert len(captured) == 2, "OFFLINE still rides the bus — only logging skips it"
    assert len(store) == 1
    _sql, params = store[0]
    assert params[1] == "meta_context"
    assert params[2] == "waking"
    inputs = json.loads(params[8])
    assert inputs["kind"] == "axis_estimate"
    assert inputs["axis"] == "meta_context"


def _biometric_feature_envelope() -> MessageEnvelope:
    now = datetime.now(timezone.utc)
    snap = FeatureSnapshot(
        user_id=USER,
        timestamp=now,
        modality=Modality.BIOMETRIC.value,
        source="watch.hr_30s",
        payload={"kind": "hr_epoch", "features": {"hr_mean": 66.0, "hr_min": 66.0,
                                                  "hr_max": 66.0, "hr_n": 30.0},
                 "extractor": "stub_passthrough"},
        i_model_id=IMODEL,
    )
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.FEATURE,
        source_role=NodeRole.WISP_EDGE,
        occurred_at=now,
        meta_context=MetaContext.SLEEP,
        consent_scope="sleep_session_v1",
        trace_id=str(uuid.uuid4()),
        payload=snap,
        i_model_id=IMODEL,
    )


def test_feature_participant_with_writer_logs_rem_prediction():
    store: list = []
    writer = PredictionLogWriter(conn_factory=lambda: _FakeConn(store))
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_PREDICTION, captured.append)
    l4f.register(bus, writer=writer)

    bus.publish(TOPIC_FEATURE, _biometric_feature_envelope())

    assert len(captured) == 1
    assert len(store) == 1
    _sql, params = store[0]
    assert params[1] == "rem"
    assert params[2] == "sleep"
    inputs = json.loads(params[8])
    assert inputs["kind"] == "feature_snapshot"
    assert inputs["features"]["hr_mean"] == 66.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
