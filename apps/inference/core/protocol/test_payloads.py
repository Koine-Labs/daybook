# apps/inference/core/protocol/test_payloads.py
import json
from datetime import datetime, timezone

import pytest

from core.protocol.payloads import (ActionDecision, FeaturePacket, OutputDirective,
                                     Prediction, SignalPacket)


def _utc():
    return datetime.now(timezone.utc)


def test_signal_packet_serializes_to_json():
    sig = SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                       intent="continuous", kind="speech_final",
                       payload={"text": "mm"}, source="mac.mic")
    d = sig.to_dict()
    json.dumps(d)  # must not raise
    assert d["modality"] == "audio" and isinstance(d["timestamp"], str)


def test_signal_packet_rejects_naive_datetime():
    with pytest.raises(ValueError):
        SignalPacket(user_id="u", timestamp=datetime(2026, 5, 28), modality="audio",
                     intent="continuous", kind="x", payload={}, source="s")


def test_signal_packet_rejects_out_of_range_confidence():
    with pytest.raises(ValueError):
        SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                     intent="continuous", kind="x", payload={}, source="s",
                     confidence=1.5)


def test_prediction_carries_action_seam_and_provenance():
    p = Prediction(user_id="u", axis="arousal_inferred", made_at=_utc(),
                   horizon_seconds=1800, distribution={"calm": 0.7}, model_id="stub.v0")
    assert p.action is None and p.provenance == "placeholder" and p.cold_start is False
    json.dumps(p.to_dict())


def test_action_decision_and_output_directive_serialize():
    dec = ActionDecision(user_id="u", decided_at=_utc(), action="hold",
                         rationale="nothing worth saying")
    out = OutputDirective(user_id="u", created_at=_utc(), channel="voice", text="hey")
    json.dumps(dec.to_dict())
    json.dumps(out.to_dict())
    assert dec.gate_trace == {} and out.delivery == {}


def test_all_timestamped_payloads_reject_naive_datetime():
    naive = datetime(2026, 5, 28)
    with pytest.raises(ValueError):
        Prediction(user_id="u", axis="a", made_at=naive, horizon_seconds=60,
                   distribution={}, model_id="m")
    with pytest.raises(ValueError):
        ActionDecision(user_id="u", decided_at=naive, action="hold", rationale="r")
    with pytest.raises(ValueError):
        OutputDirective(user_id="u", created_at=naive, channel="voice")


def test_default_factories_are_independent_instances():
    a = ActionDecision(user_id="u", decided_at=_utc(), action="hold", rationale="r")
    b = ActionDecision(user_id="u", decided_at=_utc(), action="hold", rationale="r")
    assert a.gate_trace is not b.gate_trace
    o1 = OutputDirective(user_id="u", created_at=_utc(), channel="voice")
    o2 = OutputDirective(user_id="u", created_at=_utc(), channel="voice")
    assert o1.delivery is not o2.delivery


def test_feature_packet_is_feature_snapshot_alias():
    fp = FeaturePacket(user_id="u", timestamp=_utc(), modality="audio",
                       source="mac.mic", payload={"rms": 0.1})
    assert fp.to_dict()["modality"] == "audio"
