# apps/inference/decision/test_outcome_log.py
"""DB-free tests for the L5 DecisionLogWriter + label_outcomes (fake conns)."""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.bus.bus import TOPIC_ACTION, TOPIC_PREDICTION, MessageBus  # noqa: E402
from core.protocol.enums import MetaContext, NodeRole, PayloadType  # noqa: E402
from core.protocol.envelope import MessageEnvelope  # noqa: E402
from core.protocol.payloads import ActionDecision, Prediction  # noqa: E402
from decision.outcome_log import (  # noqa: E402
    UNGRADED_COLUMNS,
    DecisionLogWriter,
    label_outcomes,
)
from decision.participant import register  # noqa: E402

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
IMODEL = "im-decision-001"

INSERT_COLUMNS = (
    "user_id", "decided_at", "trigger_kind", "context_snapshot", "decision",
    "reason", "resulting_moment_id", "mode", "content_kind", "i_model_id",
)

GATE_TRACE = {
    "policy": "default",
    "all_passed": False,
    "gates": [{"name": "meta-context", "passed": False, "detail": "not waking"}],
}


class _FakeCursor:
    def __init__(self, store: list, rows: list | None = None) -> None:
        self._store = store
        self._rows = rows or []

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self._store.append((sql, params))

    def fetchone(self) -> tuple:
        return (str(uuid.uuid4()),)

    def fetchall(self) -> list:
        return self._rows

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_a: object) -> bool:
        return False


class _FakeConn:
    def __init__(self, store: list, rows: list | None = None) -> None:
        self._store = store
        self._rows = rows
        self.committed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._store, self._rows)

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *_a: object) -> bool:
        return False


def _decision(action: str = "hold", *, gate_trace: dict[str, Any] | None = None) -> ActionDecision:
    return ActionDecision(
        user_id=USER,
        decided_at=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        action=action,  # type: ignore[arg-type]
        rationale="holding: not waking" if action == "hold" else "transition — remarking",
        mode="companion",
        content_kind="conversation_tease" if action == "interject" else None,
        gate_trace=gate_trace if gate_trace is not None else dict(GATE_TRACE),
        i_model_id=IMODEL,
    )


def test_write_inserts_exact_columns_and_values():
    store: list = []
    conn = _FakeConn(store)
    writer = DecisionLogWriter(conn_factory=lambda: conn)
    decision = _decision("interject")

    new_id = writer.write(decision, trigger_kind="prediction.audio_social_context")

    assert new_id is not None
    assert conn.committed is True
    sql, params = store[0]
    assert "INSERT INTO interject_decisions" in sql
    for col in INSERT_COLUMNS:
        assert col in sql
    assert params[0] == USER
    assert params[1] == decision.decided_at
    assert params[2] == "prediction.audio_social_context"
    assert json.loads(params[3]) == decision.gate_trace
    assert params[4] is True
    assert params[5] == decision.rationale
    assert params[6] is None
    assert params[7] == "companion"
    assert params[8] == "conversation_tease"
    assert params[9] == IMODEL


def test_hold_persists_decision_false():
    store: list = []
    writer = DecisionLogWriter(conn_factory=lambda: _FakeConn(store))

    writer.write(_decision("hold"), trigger_kind="prediction.sleep_stage")

    _sql, params = store[0]
    assert params[4] is False
    assert params[8] is None


def test_gate_trace_round_trips_as_json():
    store: list = []
    writer = DecisionLogWriter(conn_factory=lambda: _FakeConn(store))
    trace = {
        "policy": "sleep_cue",
        "all_passed": False,
        "gates": [
            {"name": "deep-sleep-suppression", "passed": False, "detail": "deep"},
            {"name": "min-interval", "passed": True, "detail": "clear"},
        ],
    }

    writer.write(_decision("hold", gate_trace=trace), trigger_kind="prediction.sleep_stage")

    _sql, params = store[0]
    assert json.loads(params[3]) == trace


def test_write_returns_none_when_db_absent():
    def _boom() -> _FakeConn:
        raise RuntimeError("DATABASE_URL not set")

    writer = DecisionLogWriter(conn_factory=_boom)
    assert writer.write(_decision(), trigger_kind="prediction.sleep_stage") is None


def test_label_outcomes_returns_ungraded_rows():
    since = datetime(2026, 6, 9, 0, 0, tzinfo=timezone.utc)
    row = (
        str(uuid.uuid4()), USER, datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        "prediction.audio_social_context", dict(GATE_TRACE), True,
        "transition — remarking", "companion", "conversation_tease", IMODEL,
    )
    store: list = []
    conn = _FakeConn(store, rows=[row])

    rows = label_outcomes(conn, since)

    sql, params = store[0]
    assert "FROM interject_decisions" in sql
    assert "user_outcome IS NULL" in sql
    assert "decided_at >= %s" in sql
    assert params == (since,)
    assert rows == [dict(zip(UNGRADED_COLUMNS, row))]


def test_label_outcomes_empty_when_no_ungraded():
    conn = _FakeConn([], rows=[])
    assert label_outcomes(conn, datetime(2026, 6, 9, tzinfo=timezone.utc)) == []


# --- participant wiring -------------------------------------------------------

def _prediction_envelope(meta: MetaContext = MetaContext.SLEEP) -> MessageEnvelope:
    pred = Prediction(
        user_id=USER,
        axis="sleep_stage",
        made_at=datetime.now(timezone.utc),
        horizon_seconds=30,
        distribution={"rem": 0.71, "core": 0.29},
        model_id="production_binary_rem",
        confidence=0.71,
        provenance="placeholder",
        i_model_id=IMODEL,
    )
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.PREDICTION,
        source_role=NodeRole.DESKTOP_COMPUTE,
        occurred_at=datetime.now(timezone.utc),
        meta_context=meta,
        consent_scope="mic_continuous_v1",
        trace_id=str(uuid.uuid4()),
        payload=pred,
        i_model_id=IMODEL,
    )


def test_participant_without_writer_is_unchanged():
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_ACTION, captured.append)
    register(bus)

    bus.publish(TOPIC_PREDICTION, _prediction_envelope())

    assert len(captured) == 1
    assert captured[0].payload.action == "hold"


def test_participant_with_writer_logs_every_decision():
    store: list = []
    writer = DecisionLogWriter(conn_factory=lambda: _FakeConn(store))
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_ACTION, captured.append)
    register(bus, writer=writer)

    bus.publish(TOPIC_PREDICTION, _prediction_envelope())

    assert len(captured) == 1
    assert len(store) == 1
    _sql, params = store[0]
    assert params[2] == "prediction.sleep_stage"
    assert params[4] is False
    assert json.loads(params[3]) == captured[0].payload.gate_trace


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
