# apps/inference/core/protocol/test_envelope.py
import json
import uuid
from datetime import datetime, timezone

import pytest

from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import (ActionDecision, BeliefState, FeaturePacket,
                                     OutputDirective, Prediction, SignalPacket)
from fusion.belief_state import AxisEstimate


def _utc():
    return datetime.now(timezone.utc)


def _env(ptype, payload):
    return MessageEnvelope(id=str(uuid.uuid4()), type=ptype,
                           source_role=NodeRole.WISP_EDGE, occurred_at=_utc(),
                           meta_context=MetaContext.WAKING, consent_scope="personal_use",
                           trace_id=str(uuid.uuid4()), payload=payload)


def test_envelope_rejects_naive_occurred_at():
    with pytest.raises(ValueError):
        MessageEnvelope(id="i", type=PayloadType.SIGNAL, source_role=NodeRole.WISP_EDGE,
                        occurred_at=datetime(2026, 5, 28), meta_context=MetaContext.WAKING,
                        consent_scope="p", trace_id="t",
                        payload=SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                                             intent="continuous", kind="x", payload={}, source="s"))


def test_envelope_serializes_every_payload_type():
    bs = BeliefState(user_id="u")
    bs.update(AxisEstimate(axis="arousal_inferred", value={"label": "calm"},
                           timestamp=_utc(), confidence=0.5, source="L3.stub"))
    cases = {
        PayloadType.SIGNAL: SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                                         intent="continuous", kind="x", payload={}, source="s"),
        PayloadType.FEATURE: FeaturePacket(user_id="u", timestamp=_utc(), modality="audio",
                                           source="s", payload={"rms": 0.1}),
        PayloadType.BELIEF: bs,
        PayloadType.PREDICTION: Prediction(user_id="u", axis="a", made_at=_utc(),
                                           horizon_seconds=60, distribution={"x": 1.0},
                                           model_id="m"),
        PayloadType.ACTION: ActionDecision(user_id="u", decided_at=_utc(), action="hold",
                                           rationale="r"),
        PayloadType.OUTPUT: OutputDirective(user_id="u", created_at=_utc(), channel="voice"),
    }
    for ptype, payload in cases.items():
        d = _env(ptype, payload).to_dict()
        json.dumps(d)  # whole envelope must be JSON-serializable
        assert d["type"] == ptype.value
        assert d["source_role"] == "wisp_edge"
        assert "payload" in d


def test_belief_payload_serializes_estimates():
    bs = BeliefState(user_id="u")
    bs.update(AxisEstimate(axis="sleep_stage", value={"label": "rem"}, timestamp=_utc(),
                           confidence=0.7, source="apple_health"))
    d = _env(PayloadType.BELIEF, bs).to_dict()
    assert d["payload"]["estimates"]["sleep_stage"]["value"] == {"label": "rem"}
