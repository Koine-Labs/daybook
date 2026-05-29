# apps/inference/core/bus/test_network.py
import socket
import threading
import time
import uuid
from datetime import datetime, timezone

import pytest

from core.bus.bus import (TOPIC_OUTPUT, TOPIC_SIGNAL, MessageBus)
from core.bus.network import HubLink, NetworkTransport, NullLink, SatelliteLink
from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import OutputDirective, SignalPacket

_DUMMY_KEY = "test-shared-key-not-a-secret"


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _utc():
    return datetime.now(timezone.utc)


def _signal_env(trace="t"):
    sig = SignalPacket(user_id="u", timestamp=_utc(), modality="biometric",
                       intent="continuous", kind="hr_30s", payload={"bpm": 61},
                       source="watch.hr_30s")
    return MessageEnvelope(id=str(uuid.uuid4()), type=PayloadType.SIGNAL,
                           source_role=NodeRole.WISP_EDGE, occurred_at=_utc(),
                           meta_context=MetaContext.WAKING, consent_scope="p",
                           trace_id=trace, payload=sig)


def _output_env(trace="o"):
    out = OutputDirective(user_id="u", created_at=_utc(), channel="voice",
                          mode="companion", text="speak this", delivery={"volume": 0.5})
    return MessageEnvelope(id=str(uuid.uuid4()), type=PayloadType.OUTPUT,
                           source_role=NodeRole.DESKTOP_COMPUTE, occurred_at=_utc(),
                           meta_context=MetaContext.WAKING, consent_scope="p",
                           trace_id=trace, payload=out)


def _wait_until(predicate, timeout=2.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ---------------------------------------------------------------------------
# C. Transport ABC contract — local half is behaviorally identical to InProcess.
# ---------------------------------------------------------------------------

def test_contract_registered_handler_receives_sent_envelope():
    t = NetworkTransport(NullLink())
    got = []
    t.register("topic.a", got.append)
    env = _signal_env()
    t.send("topic.a", env)
    assert got == [env]


def test_contract_send_to_topic_with_no_handlers_is_noop():
    t = NetworkTransport(NullLink())
    t.send("topic.empty", _signal_env())  # must not raise


def test_contract_multiple_handlers_all_receive():
    t = NetworkTransport(NullLink())
    a, b = [], []
    t.register("topic.a", a.append)
    t.register("topic.a", b.append)
    t.send("topic.a", _signal_env())
    assert len(a) == 1 and len(b) == 1


def test_messagebus_works_over_network_transport_unchanged():
    bus = MessageBus(NetworkTransport(NullLink()))
    got = []
    bus.subscribe(TOPIC_SIGNAL, got.append)
    env = _signal_env()
    bus.publish(TOPIC_SIGNAL, env)
    assert got == [env]


# ---------------------------------------------------------------------------
# B. Two-endpoint in-test relay (the keystone proof).
# ---------------------------------------------------------------------------

@pytest.fixture
def linked_buses():
    """Hub + satellite on loopback, both started; yields (hub_bus, sat_bus)."""
    port = _free_port()
    hub = HubLink(host="127.0.0.1", port=port, key=_DUMMY_KEY)
    sat = SatelliteLink(uri=f"ws://127.0.0.1:{port}", key=_DUMMY_KEY)
    hub.start()
    sat.start()
    hub_bus = MessageBus(NetworkTransport(hub))
    sat_bus = MessageBus(NetworkTransport(sat))
    assert _wait_until(lambda: hub.peer_connected and sat.peer_connected, timeout=3.0), \
        "hub and satellite did not connect"
    try:
        yield hub_bus, sat_bus
    finally:
        sat.stop()
        hub.stop()


def test_signals_up_satellite_to_hub(linked_buses):
    hub_bus, sat_bus = linked_buses
    received: list[MessageEnvelope] = []
    hub_bus.subscribe(TOPIC_SIGNAL, received.append)

    env = _signal_env(trace="trace-up")
    sat_bus.publish(TOPIC_SIGNAL, env)

    assert _wait_until(lambda: len(received) == 1), "hub handler never fired"
    got = received[0]
    assert got.trace_id == "trace-up"
    assert got.type == PayloadType.SIGNAL
    assert got.payload.kind == "hr_30s"
    assert got.payload.payload == {"bpm": 61}


def test_local_half_is_synchronous(linked_buses):
    hub_bus, sat_bus = linked_buses
    fired_inline = []
    sat_bus.subscribe(TOPIC_SIGNAL, lambda e: fired_inline.append(e))
    env = _signal_env(trace="trace-local")
    sat_bus.publish(TOPIC_SIGNAL, env)
    # No await/poll — local delivery must have happened inline during publish().
    assert fired_inline == [env]


def test_directives_down_hub_to_satellite(linked_buses):
    hub_bus, sat_bus = linked_buses
    received: list[MessageEnvelope] = []
    sat_bus.subscribe(TOPIC_OUTPUT, received.append)

    env = _output_env(trace="trace-down")
    hub_bus.publish(TOPIC_OUTPUT, env)

    assert _wait_until(lambda: len(received) == 1), "satellite handler never fired"
    got = received[0]
    assert got.trace_id == "trace-down"
    assert got.type == PayloadType.OUTPUT
    assert got.payload.text == "speak this"
    assert got.payload.channel == "voice"


def test_no_echo_back_to_publisher(linked_buses):
    hub_bus, sat_bus = linked_buses
    hub_received: list[MessageEnvelope] = []
    hub_bus.subscribe(TOPIC_OUTPUT, hub_received.append)
    # Satellite also subscribes — so the forwarded frame dispatches there, but must
    # NOT bounce back over the link and re-fire the hub handler.
    sat_received: list[MessageEnvelope] = []
    sat_bus.subscribe(TOPIC_OUTPUT, sat_received.append)

    env = _output_env(trace="trace-echo")
    hub_bus.publish(TOPIC_OUTPUT, env)

    assert _wait_until(lambda: len(sat_received) == 1), "satellite never received"
    # Give any (incorrect) echo time to arrive.
    time.sleep(0.3)
    assert len(hub_received) == 1  # only the inline local delivery, never an echo
    assert len(sat_received) == 1


def test_handler_exception_on_remote_path_is_contained(linked_buses):
    hub_bus, sat_bus = linked_buses
    good: list[MessageEnvelope] = []

    def _boom(_e):
        raise RuntimeError("handler blew up")

    hub_bus.subscribe(TOPIC_SIGNAL, _boom)
    hub_bus.subscribe(TOPIC_SIGNAL, good.append)

    sat_bus.publish(TOPIC_SIGNAL, _signal_env(trace="trace-boom-1"))
    assert _wait_until(lambda: len(good) == 1), "well-behaved handler did not receive"

    # The loop survives: a subsequent publish is still delivered.
    sat_bus.publish(TOPIC_SIGNAL, _signal_env(trace="trace-boom-2"))
    assert _wait_until(lambda: len(good) == 2), "loop died after a raising handler"


def test_malformed_frame_is_contained(linked_buses):
    hub_bus, sat_bus = linked_buses
    received: list[MessageEnvelope] = []
    hub_bus.subscribe(TOPIC_SIGNAL, received.append)

    # Inject raw garbage straight onto the satellite's outbound link.
    transport = sat_bus._transport
    transport._link.inject_raw_frame("this is not json{{{")
    transport._link.inject_raw_frame('{"topic": "l1.signal", "env": {"type": "bogus"}}')

    # The loop must survive: a subsequent valid publish still delivers.
    sat_bus.publish(TOPIC_SIGNAL, _signal_env(trace="trace-after-garbage"))
    assert _wait_until(lambda: len(received) == 1), "valid frame lost after malformed frame"
    assert received[0].trace_id == "trace-after-garbage"


# ---------------------------------------------------------------------------
# Auth + reconnect (own fixtures — these manipulate the links directly).
# ---------------------------------------------------------------------------

def test_auth_reject_wrong_key():
    port = _free_port()
    hub = HubLink(host="127.0.0.1", port=port, key=_DUMMY_KEY)
    sat = SatelliteLink(uri=f"ws://127.0.0.1:{port}", key="wrong-key")
    hub.start()
    sat.start()
    hub_bus = MessageBus(NetworkTransport(hub))
    received: list[MessageEnvelope] = []
    hub_bus.subscribe(TOPIC_SIGNAL, received.append)
    try:
        # Connection should be rejected; satellite never reaches "connected".
        assert not _wait_until(lambda: hub.peer_connected, timeout=1.5), \
            "hub accepted a wrong-key satellite"
        # Even if the satellite tries to send, nothing reaches the hub handler.
        MessageBus(NetworkTransport(sat)).publish(TOPIC_SIGNAL, _signal_env())
        time.sleep(0.3)
        assert received == []
    finally:
        sat.stop()
        hub.stop()


def test_reconnect_after_hub_restart():
    port = _free_port()
    hub = HubLink(host="127.0.0.1", port=port, key=_DUMMY_KEY)
    sat = SatelliteLink(uri=f"ws://127.0.0.1:{port}", key=_DUMMY_KEY)
    hub.start()
    sat.start()
    sat_bus = MessageBus(NetworkTransport(sat))
    hub_bus = MessageBus(NetworkTransport(hub))
    received: list[MessageEnvelope] = []
    hub_bus.subscribe(TOPIC_SIGNAL, received.append)
    try:
        assert _wait_until(lambda: hub.peer_connected and sat.peer_connected, timeout=3.0)

        # Drop the hub; satellite should detect the close and enter reconnect.
        hub.stop()
        assert _wait_until(lambda: not sat.peer_connected, timeout=3.0), \
            "satellite did not notice the drop"

        # Bring the hub back on the same port; satellite reconnects.
        hub = HubLink(host="127.0.0.1", port=port, key=_DUMMY_KEY)
        hub.start()
        hub_bus = MessageBus(NetworkTransport(hub))
        received = []
        hub_bus.subscribe(TOPIC_SIGNAL, received.append)
        assert _wait_until(lambda: hub.peer_connected and sat.peer_connected, timeout=8.0), \
            "satellite did not reconnect"

        sat_bus.publish(TOPIC_SIGNAL, _signal_env(trace="post-reconnect"))
        assert _wait_until(lambda: len(received) == 1, timeout=3.0), \
            "post-reconnect publish was not delivered"
        assert received[0].trace_id == "post-reconnect"
    finally:
        sat.stop()
        hub.stop()


def test_send_remote_on_unstarted_link_is_noop():
    # An unstarted link must not raise; local delivery still works.
    sat = SatelliteLink(uri="ws://127.0.0.1:1", key=_DUMMY_KEY)
    bus = MessageBus(NetworkTransport(sat))
    got = []
    bus.subscribe(TOPIC_SIGNAL, got.append)
    bus.publish(TOPIC_SIGNAL, _signal_env())  # must not raise, must deliver locally
    assert len(got) == 1
