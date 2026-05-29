"""Regression: the feature-based REM nowcaster is gated to the SLEEP meta-context.

The REM model is a *sleep* nowcast; scoring waking HR yields a meaningless REM
belief. Per commitment #14 (each layer selects different models per meta-context),
prediction/feature_participant.py must fire predict_rem ONLY when the inbound
envelope's meta_context is SLEEP, and degrade (no Prediction) under WAKING /
UNKNOWN — never crash the bus.

The inbound envelope mirrors test_sleep_classifier._biometric_feature_envelope:
a Modality.BIOMETRIC FeatureSnapshot carrying the model's feature vector, wrapped
as a TOPIC_FEATURE envelope. Only the meta_context varies across the cases.

Run: python -m pytest prediction/test_feature_participant_meta_gate.py -v
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.bus.bus import TOPIC_FEATURE, TOPIC_PREDICTION, MessageBus  # noqa: E402
from core.protocol.enums import MetaContext, Modality, NodeRole, PayloadType  # noqa: E402
from core.protocol.envelope import MessageEnvelope  # noqa: E402
from core.protocol.payloads import Prediction  # noqa: E402
from features.snapshot import FeatureSnapshot  # noqa: E402
from prediction import feature_participant as l4f  # noqa: E402
from prediction.predictors.sleep_classifier import REM_AXIS  # noqa: E402

USER = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"

# A minimal biometric feature dict carrying the model's core HR column so the
# snapshot is a genuine REM-scoreable epoch (constant HR; absent cols -> NaN).
_FEATS: dict[str, Any] = {
    "hr_mean": 66.0,
    "hr_min": 66.0,
    "hr_max": 66.0,
    "hr_n": 30.0,
}


def _biometric_feature_envelope(meta_context: MetaContext) -> MessageEnvelope:
    """Mirror test_sleep_classifier._biometric_feature_envelope; vary only meta_context."""
    now = datetime.now(timezone.utc)
    snap = FeatureSnapshot(
        user_id=USER,
        timestamp=now,
        modality=Modality.BIOMETRIC.value,
        source="watch.hr_30s",
        payload={"kind": "hr_epoch", "features": _FEATS, "extractor": "stub_passthrough"},
        i_model_id="im-bio-1",
    )
    return MessageEnvelope(
        id=str(uuid.uuid4()),
        type=PayloadType.FEATURE,
        source_role=NodeRole.WISP_EDGE,
        occurred_at=now,
        meta_context=meta_context,
        consent_scope="sleep_session_v1",
        trace_id=str(uuid.uuid4()),
        payload=snap,
        i_model_id="im-bio-1",
    )


def _drive(inbound: MessageEnvelope) -> list[MessageEnvelope]:
    bus = MessageBus()
    captured: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_PREDICTION, captured.append)
    l4f.register(bus)
    bus.publish(TOPIC_FEATURE, inbound)
    return captured


def test_sleep_meta_context_fires_rem_prediction():
    """A biometric snapshot under SLEEP -> exactly one "rem" Prediction."""
    inbound = _biometric_feature_envelope(MetaContext.SLEEP)
    out = _drive(inbound)

    assert len(out) == 1, "SLEEP biometric epoch must yield one rem prediction"
    env = out[0]
    assert env.type == PayloadType.PREDICTION
    assert env.trace_id == inbound.trace_id
    assert env.meta_context == MetaContext.SLEEP
    pred = env.payload
    assert isinstance(pred, Prediction)
    assert pred.axis == REM_AXIS == "rem"


def test_waking_meta_context_yields_no_prediction():
    """The identical snapshot under WAKING must NOT score REM (gate, #14)."""
    out = _drive(_biometric_feature_envelope(MetaContext.WAKING))
    assert out == [], "waking HR must not yield a meaningless rem belief"


def test_unknown_meta_context_yields_no_prediction():
    """The identical snapshot under UNKNOWN must NOT score REM (gate, #14)."""
    out = _drive(_biometric_feature_envelope(MetaContext.UNKNOWN))
    assert out == [], "unknown meta-context must not yield a rem belief"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
