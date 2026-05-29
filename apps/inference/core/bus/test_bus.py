# apps/inference/core/bus/test_bus.py
import uuid
from datetime import datetime, timezone

from core.bus.bus import (TOPIC_FEATURE, TOPIC_SIGNAL, MessageBus)
from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import SignalPacket


def _signal_env():
    sig = SignalPacket(user_id="u", timestamp=datetime.now(timezone.utc),
                       modality="audio", intent="continuous", kind="x",
                       payload={}, source="s")
    return MessageEnvelope(id=str(uuid.uuid4()), type=PayloadType.SIGNAL,
                           source_role=NodeRole.WISP_EDGE,
                           occurred_at=datetime.now(timezone.utc),
                           meta_context=MetaContext.WAKING, consent_scope="p",
                           trace_id="t", payload=sig)


def test_publish_reaches_subscriber_on_same_topic():
    bus = MessageBus()
    got = []
    bus.subscribe(TOPIC_SIGNAL, got.append)
    bus.publish(TOPIC_SIGNAL, _signal_env())
    assert len(got) == 1


def test_topics_are_isolated():
    bus = MessageBus()
    got = []
    bus.subscribe(TOPIC_FEATURE, got.append)
    bus.publish(TOPIC_SIGNAL, _signal_env())
    assert got == []


def test_topic_constants_cover_all_six_boundaries():
    from core.bus import bus as busmod
    names = {busmod.TOPIC_SIGNAL, busmod.TOPIC_FEATURE, busmod.TOPIC_BELIEF,
             busmod.TOPIC_PREDICTION, busmod.TOPIC_ACTION, busmod.TOPIC_OUTPUT}
    assert len(names) == 6
