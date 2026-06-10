"""L1 declaration producer: explicit state self-reports -> SignalPacket on the bus.

Mirrors sensors/eeg_adapter.py + watch_adapter.py. Transport-agnostic: holds only
a MessageBus, so the SAME class works over InProcessTransport (CLI/API on the Mac
today) and NetworkTransport (voice/gesture satellites later) with no change. This
is the FIRST real Intent.EXPLICIT path (commitment #10): the user volunteers a
state declaration ("I'm locked in"), not a continuous capture (#11).
"""
from __future__ import annotations

from datetime import datetime, timezone

from consent import CONSENT_SCOPES
from core.bus.bus import MessageBus
from core.protocol.enums import Intent, MetaContext, Modality
from core.protocol.envelope import MessageEnvelope
from sensors.contract import DEFAULT_USER_ID, IntentTaggedReading
from sensors.participant import emit

KIND_STATE_DECLARATION = "state_declaration"
DECLARE_SOURCE = "self_report"
CONSENT_SCOPE = CONSENT_SCOPES["self_report"]


class DeclarationBusSink:
    """Emits state_declaration SignalPackets onto a MessageBus (explicit self-report).

    `meta_context` defaults to WAKING — declarations are a waking phenomenon (#14);
    a person in deep sleep does not type/speak a state declaration.
    """

    def __init__(
        self,
        bus: MessageBus,
        *,
        user_id: str = DEFAULT_USER_ID,
        meta_context: MetaContext = MetaContext.WAKING,
    ) -> None:
        self.bus = bus
        self.user_id = user_id
        self.meta_context = meta_context

    def declare(self, text: str, *, user_id: str | None = None) -> MessageEnvelope:
        """Publish one user state declaration as an explicit TEXT SignalPacket."""
        reading = IntentTaggedReading(
            modality=Modality.TEXT.value,
            intent=Intent.EXPLICIT.value,
            kind=KIND_STATE_DECLARATION,
            payload={"text": text, "consent_scope": CONSENT_SCOPE},
            source=DECLARE_SOURCE,
            timestamp=datetime.now(timezone.utc),
            user_id=user_id or self.user_id,
        )
        return emit(
            self.bus,
            reading,
            meta_context=self.meta_context,
            consent_scope=CONSENT_SCOPE,
        )
