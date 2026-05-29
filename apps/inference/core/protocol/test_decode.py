# apps/inference/core/protocol/test_decode.py
import json
import uuid
from datetime import datetime, timezone

import pytest

from core.protocol.decode import envelope_from_dict, parse_utc
from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import (ActionDecision, BeliefState, FeaturePacket,
                                     OutputDirective, Prediction, SignalPacket)
from fusion.belief_state import AxisEstimate


def _utc():
    return datetime.now(timezone.utc)


def _env(ptype, payload, *, trace=None, target=None, i_model=None):
    return MessageEnvelope(
        id=str(uuid.uuid4()), type=ptype, source_role=NodeRole.WISP_EDGE,
        occurred_at=_utc(), meta_context=MetaContext.WAKING,
        consent_scope="personal_use", trace_id=trace or str(uuid.uuid4()),
        payload=payload, target_role=target, i_model_id=i_model,
    )


def _roundtrip(env: MessageEnvelope) -> MessageEnvelope:
    return envelope_from_dict(json.loads(json.dumps(env.to_dict())))


def test_signal_roundtrip():
    sig = SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                       intent="continuous", kind="speech_final",
                       payload={"text": "mm"}, source="mac.mic", confidence=0.4)
    env = _env(PayloadType.SIGNAL, sig)
    assert _roundtrip(env) == env


def test_feature_roundtrip():
    fp = FeaturePacket(user_id="u", timestamp=_utc(), modality="audio",
                       source="mac.mic", payload={"rms": 0.1}, duration_ms=300,
                       meta_context_hint="waking")
    env = _env(PayloadType.FEATURE, fp)
    assert _roundtrip(env) == env


def test_prediction_roundtrip():
    p = Prediction(user_id="u", axis="arousal_inferred", made_at=_utc(),
                   horizon_seconds=1800, distribution={"calm": 0.7}, model_id="stub.v0",
                   action={"action": "interject"}, provenance="calibrated", cold_start=True)
    env = _env(PayloadType.PREDICTION, p)
    assert _roundtrip(env) == env


def test_action_roundtrip():
    dec = ActionDecision(user_id="u", decided_at=_utc(), action="interject",
                         rationale="worth saying", mode="companion",
                         content_kind="tease", gate_trace={"policy": "always"})
    env = _env(PayloadType.ACTION, dec)
    assert _roundtrip(env) == env


def test_output_roundtrip():
    out = OutputDirective(user_id="u", created_at=_utc(), channel="voice",
                          mode="witness", text="rest now", delivery={"volume": 0.3})
    env = _env(PayloadType.OUTPUT, out)
    assert _roundtrip(env) == env


def test_belief_roundtrip_preserves_full_axis_shape():
    bs = BeliefState(user_id="u")
    bs.update(AxisEstimate(axis="arousal_inferred", value={"label": "calm"},
                           timestamp=_utc(), confidence=0.5, source="L3.fusion",
                           meta_context="waking", i_model_id="im-1", fresh_for_seconds=45))
    bs.update(AxisEstimate(axis="sleep_stage", value={"label": "rem", "prob": 0.71},
                           timestamp=_utc(), confidence=0.7, source="apple_health"))
    env = _env(PayloadType.BELIEF, bs)
    rebuilt = _roundtrip(env)
    assert rebuilt == env
    # Regression: inverse uses _belief_to_dict (full shape), not lossy snapshot().
    a = rebuilt.payload.estimates["arousal_inferred"]
    assert a.axis == "arousal_inferred"
    assert a.i_model_id == "im-1"
    assert a.fresh_for_seconds == 45


def test_envelope_optional_fields_roundtrip():
    sig = SignalPacket(user_id="u", timestamp=_utc(), modality="biometric",
                       intent="continuous", kind="hr_30s", payload={"bpm": 60},
                       source="watch.hr_30s")
    env = _env(PayloadType.SIGNAL, sig, target=NodeRole.DESKTOP_COMPUTE, i_model="im-42")
    rebuilt = _roundtrip(env)
    assert rebuilt == env
    assert rebuilt.target_role == NodeRole.DESKTOP_COMPUTE
    assert rebuilt.i_model_id == "im-42"


def test_trace_id_preserved():
    sig = SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                       intent="continuous", kind="x", payload={}, source="s")
    env = _env(PayloadType.SIGNAL, sig, trace="trace-keystone")
    assert _roundtrip(env).trace_id == "trace-keystone"


def test_parse_utc_parses_isoformat_to_tz_aware_utc():
    dt = _utc()
    parsed = parse_utc(dt.isoformat())
    assert parsed.tzinfo is not None
    assert parsed == dt


def test_parse_utc_normalizes_offset_to_utc():
    s = "2026-05-29T12:00:00+05:00"
    parsed = parse_utc(s)
    assert parsed.tzinfo == timezone.utc
    assert parsed.hour == 7


def test_parse_utc_rejects_naive_string():
    with pytest.raises(ValueError):
        parse_utc("2026-05-29T12:00:00")


def test_tampered_type_raises():
    sig = SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                       intent="continuous", kind="x", payload={}, source="s")
    d = _env(PayloadType.SIGNAL, sig).to_dict()
    d["type"] = "not_a_real_type"
    with pytest.raises(ValueError):
        envelope_from_dict(d)


def test_tampered_source_role_raises():
    sig = SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                       intent="continuous", kind="x", payload={}, source="s")
    d = _env(PayloadType.SIGNAL, sig).to_dict()
    d["source_role"] = "mars_base"
    with pytest.raises(ValueError):
        envelope_from_dict(d)


def test_tampered_meta_context_raises():
    sig = SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                       intent="continuous", kind="x", payload={}, source="s")
    d = _env(PayloadType.SIGNAL, sig).to_dict()
    d["meta_context"] = "lucid"
    with pytest.raises(ValueError):
        envelope_from_dict(d)


def test_decode_reenforces_naive_timestamp_invariant():
    sig = SignalPacket(user_id="u", timestamp=_utc(), modality="audio",
                       intent="continuous", kind="x", payload={}, source="s")
    d = _env(PayloadType.SIGNAL, sig).to_dict()
    d["payload"]["timestamp"] = "2026-05-29T12:00:00"  # naive
    with pytest.raises(ValueError):
        envelope_from_dict(d)
