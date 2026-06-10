# apps/inference/prediction/feature_participant.py
"""L4 feature-based participant — biometric FeatureSnapshot -> "rem" Prediction.

The standard L4 participant (participant.py) consumes L3 BeliefStates. The REM
nowcaster is different: it is feature-based (commitment #16 stand-alone per-axis
predictor) and reads the 24 pure-biometric features straight off an L2
FeatureSnapshot. So it subscribes TOPIC_FEATURE directly, scores the current
epoch, and publishes one "rem" Prediction on TOPIC_PREDICTION.

It only fires on biometric snapshots that actually carry the model's feature
vector AND only under the SLEEP meta-context: the REM model is a sleep nowcast,
so waking HR would yield a meaningless REM belief. This is commitment #14 — L4
selects different models per meta-context — so anything else (other modalities,
offline sentinels, feature-less snapshots, non-SLEEP meta-contexts) is skipped:
degrade, never crash the bus. Every outbound envelope inherits trace_id /
meta_context / consent_scope / i_model_id via core/layer.py so one stimulus stays
followable L1->L6 (#14/#11/#1).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.bus.bus import TOPIC_FEATURE, TOPIC_PREDICTION, MessageBus
from core.layer import forward_envelope
from core.nodes import role_for
from core.protocol.enums import MetaContext, Modality, PayloadType
from core.protocol.envelope import MessageEnvelope
from features.snapshot import FeatureSnapshot

from .prediction_log import PredictionLogWriter, feature_inputs
from .predictors.sleep_classifier import DEFAULT_PREDICTOR, REM_AXIS

SOURCE_ROLE = role_for("L4.prediction")

_BIOMETRIC = Modality.BIOMETRIC.value
# Sentinel key the L2 offline extractor stamps on feature-less snapshots.
_OFFLINE_FEATURE = "__offline__"


def _feature_dict(snapshot: FeatureSnapshot) -> dict[str, Any] | None:
    """Pull the model feature dict from a snapshot payload, or None if absent.

    Accepts either the features sitting at the payload top level or nested under
    payload["features"] (the L2 stub passthrough shape). Requires that the
    predictor's required feature columns are present; otherwise returns None so
    the caller skips (a partial biometric packet is not a REM-scoreable epoch).
    """
    payload = snapshot.payload
    if not isinstance(payload, dict) or payload.get(_OFFLINE_FEATURE):
        return None
    nested = payload.get("features")
    feats = nested if isinstance(nested, dict) else payload
    if not isinstance(feats, dict):
        return None
    cols = DEFAULT_PREDICTOR.feature_cols
    # Require at least the core HR feature; the model handles the rest as NaN,
    # but a snapshot carrying none of the 24 columns is not a biometric epoch.
    if not any(c in feats for c in cols):
        return None
    return feats


def handle_feature(
    bus: MessageBus,
    inbound: MessageEnvelope,
    *,
    writer: PredictionLogWriter | None = None,
) -> MessageEnvelope | None:
    """Score one biometric FeatureSnapshot into a "rem" Prediction; else skip.

    `writer` is the optional learning-loop seam (#13/#16): when provided, the
    prediction is persisted to prediction_log; default None keeps the DB-free
    behavior exactly.
    """
    payload = inbound.payload
    if not isinstance(payload, FeatureSnapshot):
        return None  # not ours; degrade, never crash the bus
    if payload.modality != _BIOMETRIC:
        return None
    feats = _feature_dict(payload)
    if feats is None:
        return None
    # REM is a sleep nowcast; waking HR yields a meaningless belief (#14).
    if inbound.meta_context != MetaContext.SLEEP:
        return None

    now = datetime.now(timezone.utc)
    pred = DEFAULT_PREDICTOR.predict_rem(
        user_id=payload.user_id,
        features=feats,
        now=now,
        i_model_id=inbound.i_model_id,
    )
    out = forward_envelope(
        inbound,
        ptype=PayloadType.PREDICTION,
        payload=pred,
        source_role=SOURCE_ROLE,
    )
    bus.publish(TOPIC_PREDICTION, out)
    if writer is not None:
        writer.write(
            pred,
            meta_context=inbound.meta_context.value,
            inputs_used=feature_inputs(feats),
        )
    return out


def register(bus: MessageBus, *, writer: PredictionLogWriter | None = None) -> None:
    """Subscribe the feature-based REM participant to TOPIC_FEATURE (optional writer)."""

    def _on_feature(env: MessageEnvelope) -> None:
        handle_feature(bus, env, writer=writer)

    bus.subscribe(TOPIC_FEATURE, _on_feature)


__all__ = ["register", "handle_feature", "SOURCE_ROLE", "REM_AXIS"]
