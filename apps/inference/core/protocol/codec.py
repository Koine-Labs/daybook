# apps/inference/core/protocol/codec.py
"""Payload <-> dict serialization (the wire seam).

In-process delivery passes Python objects untouched; this codec exists for the
future NetworkTransport and for tests that prove every payload is JSON-ready.
BeliefState is serialized explicitly here so fusion/ stays untouched.
"""
from __future__ import annotations

from typing import Any

from core.protocol.enums import PayloadType
from fusion.belief_state import AxisEstimate, BeliefState


def _axis_to_dict(est: AxisEstimate) -> dict[str, Any]:
    return {
        "axis": est.axis,
        "value": est.value,
        "timestamp": est.timestamp.isoformat(),
        "confidence": est.confidence,
        "source": est.source,
        "meta_context": est.meta_context,
        "i_model_id": est.i_model_id,
        "fresh_for_seconds": est.fresh_for_seconds,
    }


def _belief_to_dict(bs: BeliefState) -> dict[str, Any]:
    return {
        "user_id": bs.user_id,
        "estimates": {ax: _axis_to_dict(e) for ax, e in bs.estimates.items()},
    }


def payload_to_dict(ptype: PayloadType, payload: Any) -> dict[str, Any]:
    """Serialize a payload to a JSON-ready dict, dispatched by its type."""
    if ptype == PayloadType.BELIEF:
        return _belief_to_dict(payload)
    if hasattr(payload, "to_dict"):
        return payload.to_dict()
    raise TypeError(f"no serializer for payload type {ptype}")
