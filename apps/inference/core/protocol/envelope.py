# apps/inference/core/protocol/envelope.py
"""MessageEnvelope — the wrapper every message rides in across layers and nodes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.protocol.codec import payload_to_dict
from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.payloads import (ActionDecision, BeliefState, FeatureSnapshot,
                                     OutputDirective, Prediction, SignalPacket)

Payload = (SignalPacket | FeatureSnapshot | BeliefState | Prediction
           | ActionDecision | OutputDirective)


@dataclass
class MessageEnvelope:
    """Routing + context + consent wrapper around one layer payload.

    Carries meta_context (#14), consent_scope (#11), i_model_id (#1), and a
    trace_id so one stimulus can be followed through all six layers.
    """

    id: str
    type: PayloadType
    source_role: NodeRole
    occurred_at: datetime             # tz-aware UTC
    meta_context: MetaContext
    consent_scope: str
    trace_id: str
    payload: Payload
    schema_version: int = 1
    target_role: NodeRole | None = None
    i_model_id: str | None = None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError("MessageEnvelope.occurred_at must be tz-aware UTC")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "schema_version": self.schema_version,
            "source_role": self.source_role.value,
            "target_role": self.target_role.value if self.target_role else None,
            "occurred_at": self.occurred_at.isoformat(),
            "meta_context": self.meta_context.value,
            "consent_scope": self.consent_scope,
            "trace_id": self.trace_id,
            "i_model_id": self.i_model_id,
            "payload": payload_to_dict(self.type, self.payload),
        }
