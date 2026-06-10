"""Tests for the state_declared orchestration arc."""
from __future__ import annotations

import pytest

from labels import LabelSource
from state import declare


@pytest.fixture(autouse=True)
def _mock_db(monkeypatch):
    """Mock all DB writes so the arc is DB-free in CI."""
    written_labels = []
    written_beliefs = []
    monkeypatch.setattr(
        declare.labels_ledger, "record_label", lambda rec: written_labels.append(rec) or "id"
    )
    # The arc now writes labels atomically via record_labels; mock returns the
    # written count (len) so declare_state's reported count reflects the mock.
    monkeypatch.setattr(
        declare.labels_ledger,
        "record_labels",
        lambda recs: (written_labels.extend(recs), len(recs))[1],
    )
    monkeypatch.setattr(
        declare, "write_axis_estimate", lambda uid, est: written_beliefs.append((uid, est)) or "id"
    )
    return {"labels": written_labels, "beliefs": written_beliefs}


def test_declare_state_offline_yields_belief_and_self_report_labels(_mock_db):
    result = declare.declare_state("wiped but wired", user_id="u1", offline=True)

    assert result["axis"] == "state_declared"
    assert result["classifier"] == "quickpick"
    assert result["labels"] >= 2
    assert result["persisted"] is True

    # one state_declared belief persisted
    assert len(_mock_db["beliefs"]) == 1
    uid, est = _mock_db["beliefs"][0]
    assert uid == "u1"
    assert est.axis == "state_declared"
    assert est.source == LabelSource.SELF_REPORT.value
    assert est.value["scaffold"] is False

    # per-claim fatigue + arousal self_report labels. arousal joins to the
    # inferred axis name (canonical_axis), fatigue keeps its own name (#5).
    axes = {rec.axis for rec in _mock_db["labels"]}
    assert "fatigue" in axes
    assert "arousal_inferred" in axes
    assert "arousal" not in axes
    for rec in _mock_db["labels"]:
        assert rec.source == LabelSource.SELF_REPORT
        assert rec.provenance["declaration_text"] == "wiped but wired"
        assert rec.provenance["classifier"] == "quickpick"
        assert rec.consent_scope == "self_report_v1"


def test_declare_state_no_persist_skips_db(_mock_db):
    result = declare.declare_state("I'm exhausted", user_id="u1", offline=True, persist=False)
    assert _mock_db["beliefs"] == []
    assert _mock_db["labels"] == []
    assert result["persisted"] is False
    # the belief was still produced; labels were built but not written
    assert result["axis"] == "state_declared"
    assert result["labels"] >= 1


def test_record_self_report_labels_ignores_non_declaration_belief():
    from core.protocol.payloads import BeliefState
    from types import SimpleNamespace

    belief = BeliefState(user_id="u1")  # no state_declared estimate
    env = SimpleNamespace(payload=belief)
    assert declare.record_self_report_labels(env, persist=False) == []


def test_declare_state_garbled_text_yields_no_belief(_mock_db):
    """An empty/garbled declaration parses to no claims -> OFFLINE, no labels (BUG)."""
    result = declare.declare_state("asdkjfh qwlekjr", user_id="u1", offline=True)
    assert result["axis"] is None
    assert result["labels"] == 0
    assert result["persisted"] is False
    assert _mock_db["labels"] == []
    assert _mock_db["beliefs"] == []


def test_declare_state_wired_anxious_label_axis_is_arousal_inferred(_mock_db):
    """A 'wired/anxious' declaration stores its arousal label under arousal_inferred (#5)."""
    declare.declare_state("wired and anxious", user_id="u1", offline=True)
    axes = {rec.axis for rec in _mock_db["labels"]}
    assert "arousal_inferred" in axes
    assert "arousal" not in axes


def test_normal_fusion_tick_never_writes_to_the_label_ledger(monkeypatch):
    """D1: a non-declaration fusion tick touches NEITHER ledger writer (label!=belief)."""
    from datetime import datetime, timezone

    from core.protocol.enums import Intent, Modality
    from core.protocol.payloads import SignalPacket
    from features import participant as features_participant
    from fusion import participant as fusion_participant
    from core.bus.bus import TOPIC_SIGNAL, MessageBus
    from sensors.participant import emit
    from sensors.contract import IntentTaggedReading

    def _boom(*_a, **_k):
        raise AssertionError("ledger writer must not be called on a non-declaration tick")

    monkeypatch.setattr(declare.labels_ledger, "record_label", _boom)
    monkeypatch.setattr(declare.labels_ledger, "record_labels", _boom)

    bus = MessageBus()
    features_participant.register(bus)
    fusion_participant.register(bus)

    reading = IntentTaggedReading(
        modality=Modality.AUDIO.value,
        intent=Intent.CONTINUOUS.value,
        kind="audio_social_context",
        payload={"speaker_count": 2, "is_user_speaking": True},
        source="mic.continuous",
        timestamp=datetime.now(timezone.utc),
        user_id="u1",
    )
    emit(bus, reading)  # a normal continuous tick — must not invoke any ledger writer.
