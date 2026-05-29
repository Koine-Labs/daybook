# apps/inference/decision/test_participant.py
"""Smoke + unit tests for the L5 Decision participant and policies."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.bus.bus import TOPIC_ACTION, TOPIC_PREDICTION, MessageBus
from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import ActionDecision, Prediction

from decision.intent_dispatch import policy_name_for
from decision.participant import decide, register
from decision.policy import DecisionContext
from decision.registry import DECISION_OFFLINE, get_policy, select_policy

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
TRACE = str(uuid.uuid4())
IMODEL = "im-decision-001"


def _prediction(axis: str = "sleep_stage") -> Prediction:
    return Prediction(
        user_id=USER,
        axis=axis,
        made_at=datetime.now(timezone.utc),
        horizon_seconds=30,
        distribution={"rem": 0.71, "core": 0.29},
        model_id="production_binary_rem",
        confidence=0.71,
        provenance="placeholder",
        i_model_id=IMODEL,
    )


def _inbound(meta: MetaContext = MetaContext.SLEEP) -> MessageEnvelope:
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.PREDICTION,
        source_role=NodeRole.DESKTOP_COMPUTE,
        occurred_at=datetime.now(timezone.utc),
        meta_context=meta,
        consent_scope="mic_continuous_v1",
        trace_id=TRACE,
        payload=_prediction(),
        i_model_id=IMODEL,
    )


def _ctx(meta: MetaContext = MetaContext.SLEEP) -> DecisionContext:
    return DecisionContext(
        user_id=USER, prediction=_prediction(), meta_context=meta,
        consent_scope="c", now=datetime.now(timezone.utc), i_model_id=IMODEL,
    )


def test_participant_publishes_action_on_action_topic():
    bus = MessageBus()
    got: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_ACTION, got.append)
    register(bus)

    bus.publish(TOPIC_PREDICTION, _inbound())

    assert len(got) == 1
    out = got[0]
    assert out.type == PayloadType.ACTION
    assert isinstance(out.payload, ActionDecision)


def test_outbound_inherits_trace_meta_consent_imodel():
    out = decide(_inbound(MetaContext.SLEEP))
    assert out.trace_id == TRACE
    assert out.meta_context == MetaContext.SLEEP
    assert out.consent_scope == "mic_continuous_v1"
    assert out.i_model_id == IMODEL
    assert out.source_role == NodeRole.DESKTOP_COMPUTE


def test_default_action_is_hold_with_populated_gate_trace():
    out = decide(_inbound(MetaContext.SLEEP))
    decision: ActionDecision = out.payload
    assert decision.action == "hold"
    assert decision.gate_trace["policy"] == "sleep_cue"
    assert decision.gate_trace["all_passed"] is False
    gates = decision.gate_trace["gates"]
    names = {g["name"] for g in gates}
    assert names == {
        "deep-sleep-suppression", "min-interval", "max-per-night",
        "stale-axis", "unknown-speaker",
    }
    assert all(g["passed"] is False for g in gates)


def test_sleep_cue_mode_is_witness():
    decision: ActionDecision = decide(_inbound(MetaContext.SLEEP)).payload
    assert decision.mode == "witness"


def test_waking_routes_to_default_policy_and_holds():
    out = decide(_inbound(MetaContext.WAKING))
    decision: ActionDecision = out.payload
    assert decision.action == "hold"
    assert decision.mode == "companion"
    assert decision.gate_trace["policy"] == "default"
    assert decision.gate_trace["gates"]  # at least one gate recorded


def test_intent_dispatch_maps_meta_context():
    assert policy_name_for(_ctx(MetaContext.SLEEP)) == "sleep_cue"
    assert policy_name_for(_ctx(MetaContext.WAKING)) == "default"
    assert policy_name_for(_ctx(MetaContext.UNKNOWN)) == "default"


def test_offline_sentinel_holds():
    offline = get_policy("no-such-policy")
    assert offline is DECISION_OFFLINE
    decision = offline.decide(_ctx())
    assert decision.action == "hold"
    assert decision.gate_trace["offline"] is True


def test_select_policy_resolves_known_policies():
    assert select_policy(_ctx(MetaContext.SLEEP)).name == "sleep_cue"
    assert select_policy(_ctx(MetaContext.WAKING)).name == "default"


def test_decision_payload_is_json_serializable():
    decision: ActionDecision = decide(_inbound()).payload
    d = decision.to_dict()
    assert d["action"] == "hold"
    assert isinstance(d["decided_at"], str)  # isoformat
    assert d["gate_trace"]["policy"] == "sleep_cue"
