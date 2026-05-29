"""L1 sensors / capture — the entry point of the nervous system.

L1 has no input topic; it PRODUCES SignalPacket envelopes on TOPIC_SIGNAL.
Readings enter as `IntentTaggedReading` (commitment #10: modality + intent),
convert to a `SignalPacket`, and are emitted via `participant.emit`.
"""
from __future__ import annotations

from sensors.contract import IntentTaggedReading, to_signal_packet
from sensors.participant import emit

__all__ = ["IntentTaggedReading", "to_signal_packet", "emit"]
