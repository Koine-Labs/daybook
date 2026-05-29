# apps/inference/core/bus/test_transport.py
import uuid
from datetime import datetime, timezone

from core.bus.transport import InProcessTransport
from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import SignalPacket


def _signal_env(trace="t"):
    sig = SignalPacket(user_id="u", timestamp=datetime.now(timezone.utc),
                       modality="audio", intent="continuous", kind="x",
                       payload={}, source="s")
    return MessageEnvelope(id=str(uuid.uuid4()), type=PayloadType.SIGNAL,
                           source_role=NodeRole.WISP_EDGE,
                           occurred_at=datetime.now(timezone.utc),
                           meta_context=MetaContext.WAKING, consent_scope="p",
                           trace_id=trace, payload=sig)


def test_registered_handler_receives_sent_envelope():
    t = InProcessTransport()
    got = []
    t.register("topic.a", got.append)
    env = _signal_env()
    t.send("topic.a", env)
    assert got == [env]


def test_send_to_topic_with_no_handlers_is_noop():
    t = InProcessTransport()
    t.send("topic.empty", _signal_env())  # must not raise


def test_multiple_handlers_all_receive():
    t = InProcessTransport()
    a, b = [], []
    t.register("topic.a", a.append)
    t.register("topic.a", b.append)
    t.send("topic.a", _signal_env())
    assert len(a) == 1 and len(b) == 1
