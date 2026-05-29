# apps/inference/core/bus/bus.py
"""MessageBus — the publish/subscribe API layers use, over a Transport."""
from __future__ import annotations

from core.bus.transport import Handler, InProcessTransport, Transport
from core.protocol.envelope import MessageEnvelope

# One topic per layer boundary.
TOPIC_SIGNAL = "l1.signal"
TOPIC_FEATURE = "l2.feature"
TOPIC_BELIEF = "l3.belief"
TOPIC_PREDICTION = "l4.prediction"
TOPIC_ACTION = "l5.action"
TOPIC_OUTPUT = "l6.output"


class MessageBus:
    """Ergonomic publish/subscribe over a pluggable Transport."""

    def __init__(self, transport: Transport | None = None) -> None:
        self._transport = transport or InProcessTransport()

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._transport.register(topic, handler)

    def publish(self, topic: str, env: MessageEnvelope) -> None:
        self._transport.send(topic, env)
