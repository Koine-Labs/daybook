# apps/inference/prediction/predictors/stub.py
"""Naive placeholder predictor — the honest v1 scaffold (commitment #16).

It does NOT forecast. It returns a flat/uninformative distribution and
cold_start=True so no downstream layer mistakes scaffold output for a
calibrated forecast. When the axis estimate is categorical, the flat
distribution is uniform over the *observed* category plus an explicit
"persistence-only" note; when it's a scalar/{mean,variance}, it carries the
last value forward with inflated variance. Either way: provenance="placeholder".

This is the seam that the LeWM-recipe world model replaces axis-by-axis as the
data flywheel fills, without changing the Predictor contract.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.protocol.payloads import Prediction
from fusion.belief_state import AxisEstimate

STUB_MODEL_ID = "prediction.stub.persistence.v0"


class StubPredictor:
    """Persistence placeholder: assumes state is unchanged, with no confidence."""

    model_id: str = STUB_MODEL_ID

    def predict(
        self,
        *,
        axis: str,
        estimate: AxisEstimate,
        horizon_seconds: int,
        action: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> Prediction:
        """Return a flat persistence Prediction; never fabricate confidence."""
        if now is None:
            now = datetime.now(timezone.utc)
        return Prediction(
            user_id=_user_id_or_unknown(estimate),
            axis=axis,
            made_at=now,
            horizon_seconds=horizon_seconds,
            distribution=_flat_distribution(estimate),
            model_id=self.model_id,
            confidence=None,  # uninformative — not a calibrated number
            action=action,
            provenance="placeholder",
            cold_start=True,
            i_model_id=estimate.i_model_id,
        )


def _user_id_or_unknown(estimate: AxisEstimate) -> str:
    # AxisEstimate carries no user_id; the participant overrides this from the
    # BeliefState. Kept defensive so the predictor is usable standalone too.
    return getattr(estimate, "user_id", "unknown")


def _flat_distribution(estimate: AxisEstimate) -> dict[str, Any]:
    """Uninformative carry-forward of the current estimate — no invented numbers."""
    return {
        "kind": "persistence",
        "informative": False,
        "carried_value": estimate.value,
        "note": "placeholder: current state assumed to persist; no learned dynamics",
    }
