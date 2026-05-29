# apps/inference/prediction/interface.py
"""L4 prediction contract — predict(axis, horizon, action) and the OFFLINE sentinel.

The `action` parameter is the counterfactual seam preserved from day one
(commitments #15/#16): v1 predictors ignore it, but the interface already
carries the action-conditioning branch toward the JEPA world model.

PREDICTION_OFFLINE mirrors fusion's OFFLINE idea — it is *returned* (never
raised) when no predictor covers an (axis, meta_context). It is a Prediction
with a flat distribution, zero confidence, and provenance="placeholder", so
downstream L5 can treat "no answer" as a well-formed packet rather than a crash.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from core.protocol.payloads import Prediction
from fusion.belief_state import AxisEstimate

OFFLINE_MODEL_ID = "prediction.offline.v0"


@runtime_checkable
class Predictor(Protocol):
    """One registered predictor for an axis. Returns a well-formed Prediction."""

    model_id: str

    def predict(
        self,
        *,
        axis: str,
        estimate: AxisEstimate,
        horizon_seconds: int,
        action: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> Prediction: ...


def make_offline(
    *,
    user_id: str,
    axis: str,
    horizon_seconds: int,
    action: dict[str, Any] | None = None,
    now: datetime | None = None,
    i_model_id: str | None = None,
) -> Prediction:
    """Build the OFFLINE sentinel Prediction for an unpredictable axis."""
    if now is None:
        now = datetime.now(timezone.utc)
    return Prediction(
        user_id=user_id,
        axis=axis,
        made_at=now,
        horizon_seconds=horizon_seconds,
        distribution={"kind": "offline", "reason": "no_predictor_registered"},
        model_id=OFFLINE_MODEL_ID,
        confidence=None,
        action=action,
        provenance="placeholder",
        cold_start=True,
        i_model_id=i_model_id,
    )


def predict(
    *,
    user_id: str,
    axis: str,
    estimate: AxisEstimate | None,
    horizon_seconds: int,
    predictor: Predictor | None,
    action: dict[str, Any] | None = None,
    now: datetime | None = None,
    i_model_id: str | None = None,
) -> Prediction:
    """Forecast one axis. Returns PREDICTION_OFFLINE when no predictor/estimate."""
    if predictor is None or estimate is None:
        return make_offline(
            user_id=user_id,
            axis=axis,
            horizon_seconds=horizon_seconds,
            action=action,
            now=now,
            i_model_id=i_model_id,
        )
    return predictor.predict(
        axis=axis,
        estimate=estimate,
        horizon_seconds=horizon_seconds,
        action=action,
        now=now,
    )


# Module-level marker so callers can identify an offline result without
# inspecting field-by-field: `pred.model_id == PREDICTION_OFFLINE`.
PREDICTION_OFFLINE = OFFLINE_MODEL_ID
