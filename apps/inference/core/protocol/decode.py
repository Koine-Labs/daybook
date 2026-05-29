# apps/inference/core/protocol/decode.py
"""Inverse codec (the wire-decode seam): dict -> payload + MessageEnvelope.

The mirror of codec.py / *.to_dict(): NetworkTransport receives a JSON dict and
rebuilds the typed object graph. BeliefState is rebuilt explicitly here (inverse
of codec._belief_to_dict) so fusion/ stays untouched. Payload __post_init__ re-runs
on every decode, so tz-aware + confidence-range invariants are re-enforced for free.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from core.protocol.enums import MetaContext, NodeRole, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.protocol.payloads import (ActionDecision, FeatureSnapshot, OutputDirective,
                                     Prediction, SignalPacket)
from fusion.belief_state import DEFAULT_FRESH_SECONDS, AxisEstimate, BeliefState


def parse_utc(s: str) -> datetime:
    """Parse an ISO-8601 string to a tz-aware UTC datetime; reject naive input."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"timestamp is not tz-aware: {s!r}")
    return dt.astimezone(timezone.utc)


def signal_from_dict(d: dict[str, Any]) -> SignalPacket:
    return SignalPacket(
        user_id=d["user_id"], timestamp=parse_utc(d["timestamp"]),
        modality=d["modality"], intent=d["intent"], kind=d["kind"],
        payload=d["payload"], source=d["source"],
        confidence=d.get("confidence"), i_model_id=d.get("i_model_id"),
    )


def feature_from_dict(d: dict[str, Any]) -> FeatureSnapshot:
    return FeatureSnapshot(
        user_id=d["user_id"], timestamp=parse_utc(d["timestamp"]),
        modality=d["modality"], source=d["source"], payload=d["payload"],
        intent=d.get("intent", "continuous"), confidence=d.get("confidence"),
        duration_ms=d.get("duration_ms"), meta_context_hint=d.get("meta_context_hint"),
        i_model_id=d.get("i_model_id"),
    )


def prediction_from_dict(d: dict[str, Any]) -> Prediction:
    return Prediction(
        user_id=d["user_id"], axis=d["axis"], made_at=parse_utc(d["made_at"]),
        horizon_seconds=d["horizon_seconds"], distribution=d["distribution"],
        model_id=d["model_id"], confidence=d.get("confidence"), action=d.get("action"),
        provenance=d.get("provenance", "placeholder"), cold_start=d.get("cold_start", False),
        i_model_id=d.get("i_model_id"),
    )


def action_from_dict(d: dict[str, Any]) -> ActionDecision:
    return ActionDecision(
        user_id=d["user_id"], decided_at=parse_utc(d["decided_at"]),
        action=d["action"], rationale=d["rationale"], mode=d.get("mode"),
        content_kind=d.get("content_kind"), gate_trace=d.get("gate_trace", {}),
        i_model_id=d.get("i_model_id"),
    )


def output_from_dict(d: dict[str, Any]) -> OutputDirective:
    return OutputDirective(
        user_id=d["user_id"], created_at=parse_utc(d["created_at"]),
        channel=d["channel"], mode=d.get("mode"), text=d.get("text"),
        delivery=d.get("delivery", {}), i_model_id=d.get("i_model_id"),
    )


def _axis_from_dict(d: dict[str, Any]) -> AxisEstimate:
    return AxisEstimate(
        axis=d["axis"], value=d["value"], timestamp=parse_utc(d["timestamp"]),
        confidence=d["confidence"], source=d["source"],
        meta_context=d.get("meta_context"), i_model_id=d.get("i_model_id"),
        fresh_for_seconds=d.get("fresh_for_seconds", DEFAULT_FRESH_SECONDS),
    )


def belief_from_dict(d: dict[str, Any]) -> BeliefState:
    """Invert codec._belief_to_dict (full shape), NOT lossy BeliefState.snapshot()."""
    return BeliefState(
        user_id=d["user_id"],
        estimates={ax: _axis_from_dict(e) for ax, e in d["estimates"].items()},
    )


_PAYLOAD_DECODERS: dict[PayloadType, Callable[[dict[str, Any]], Any]] = {
    PayloadType.SIGNAL: signal_from_dict,
    PayloadType.FEATURE: feature_from_dict,
    PayloadType.BELIEF: belief_from_dict,
    PayloadType.PREDICTION: prediction_from_dict,
    PayloadType.ACTION: action_from_dict,
    PayloadType.OUTPUT: output_from_dict,
}


def decode_payload(ptype: PayloadType, d: dict[str, Any]) -> Any:
    """Rebuild a payload from its dict, dispatched by PayloadType."""
    return _PAYLOAD_DECODERS[ptype](d)


def envelope_from_dict(d: dict[str, Any]) -> MessageEnvelope:
    """Rebuild a MessageEnvelope (+ its payload) from a JSON dict — inverse of to_dict()."""
    ptype = PayloadType(d["type"])
    payload = decode_payload(ptype, d["payload"])
    target = d.get("target_role")
    return MessageEnvelope(
        id=d["id"], type=ptype,
        source_role=NodeRole(d["source_role"]),
        occurred_at=parse_utc(d["occurred_at"]),
        meta_context=MetaContext(d["meta_context"]),
        consent_scope=d["consent_scope"], trace_id=d["trace_id"],
        payload=payload,
        schema_version=d.get("schema_version", 1),
        target_role=NodeRole(target) if target else None,
        i_model_id=d.get("i_model_id"),
    )
