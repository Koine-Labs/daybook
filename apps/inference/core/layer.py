# apps/inference/core/layer.py
"""Shared bus-participant helper — the consistency anchor every layer uses.

`forward_envelope` builds a layer's outbound MessageEnvelope from the inbound
one, inheriting trace_id / meta_context / consent_scope / i_model_id so one
stimulus stays followable across all six layers (#14 context, #11 consent,
#1 i_model). Each layer supplies only what it produced: a new payload + type +
its own NodeRole.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.protocol.enums import NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope, Payload


def forward_envelope(
    inbound: MessageEnvelope,
    *,
    ptype: PayloadType,
    payload: Payload,
    source_role: NodeRole,
    target_role: NodeRole | None = None,
) -> MessageEnvelope:
    """Wrap a layer's output, inheriting trace + context + consent from inbound."""
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=ptype,
        source_role=source_role,
        occurred_at=datetime.now(timezone.utc),
        meta_context=inbound.meta_context,
        consent_scope=inbound.consent_scope,
        trace_id=inbound.trace_id,
        payload=payload,
        target_role=target_role,
        i_model_id=inbound.i_model_id,
    )
