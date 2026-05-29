"""Transport seam: how envelopes are physically delivered.

Today: InProcessTransport (synchronous, single process). Later: a NetworkTransport
(broker / HTTP relay) implements the same interface so layers never change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Callable

from core.protocol.envelope import MessageEnvelope

Handler = Callable[[MessageEnvelope], None]


class Transport(ABC):
    """Delivers envelopes to handlers registered on a topic."""

    @abstractmethod
    def register(self, topic: str, handler: Handler) -> None: ...

    @abstractmethod
    def send(self, topic: str, env: MessageEnvelope) -> None: ...


class InProcessTransport(Transport):
    """In-memory synchronous delivery: send() calls each handler inline."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def register(self, topic: str, handler: Handler) -> None:
        self._handlers[topic].append(handler)

    def send(self, topic: str, env: MessageEnvelope) -> None:
        for handler in list(self._handlers.get(topic, [])):
            handler(env)
