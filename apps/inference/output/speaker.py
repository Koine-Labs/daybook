# apps/inference/output/speaker.py
"""L6 TTS output sink — TOPIC_OUTPUT → spoken voice.

Subscribes the output topic and speaks the text of *voice* OutputDirectives so
Regis actually surfaces through the pipeline (commitment #3: voice is the
primary output surface). The speak callable is injectable so tests can record
spoken strings without touching the speaker/network; the default lazily wraps
the real audio TTS path (audio.streaming.speak_streaming), imported inside the
default so importing output.speaker never pulls audio into the import graph.

Speak policy (consistent with channels.py / participant.py):
- channel == "voice" with non-empty text → speak it.
- silent / visual / hold directives (text is None or empty) → never spoken;
  we never speak silence and never speak over a sleeper (#14).
- foreign payloads on the topic → ignored, never crash.
"""
from __future__ import annotations

import logging
from typing import Callable

from core.bus.bus import TOPIC_OUTPUT, MessageBus
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import OutputDirective

Speak = Callable[[str], None]

_log = logging.getLogger(__name__)


def _default_speak(text: str) -> None:
    """Real TTS sink. Lazy import keeps audio out of the module import graph."""
    from audio.streaming import speak_streaming  # lazy: never imported in tests

    speak_streaming(text)


class SpeakerSink:
    """L6 organ: OutputDirective → spoken voice via an injectable speak callable."""

    def __init__(self, bus: MessageBus, *, speak: Speak | None = None) -> None:
        self._bus = bus
        self._speak: Speak = speak or _default_speak

    def _handle(self, env: MessageEnvelope) -> None:
        directive = env.payload
        if not isinstance(directive, OutputDirective):
            return  # foreign payload on the topic; ignore
        if directive.channel != "voice":
            return  # silent / visual / haptic → nothing to speak
        text = directive.text
        if not text:
            return  # never speak silence (silent directives carry text=None)
        try:
            self._speak(text)
        except Exception:  # leaf output sink: a TTS/device error must not crash the arc
            _log.exception("TTS speak failed; dropping this utterance")


def register_speaker(bus: MessageBus, *, speak: Speak | None = None) -> SpeakerSink:
    """Subscribe the TTS sink to TOPIC_OUTPUT; returns it for test access."""
    sink = SpeakerSink(bus, speak=speak)
    bus.subscribe(TOPIC_OUTPUT, sink._handle)
    return sink
