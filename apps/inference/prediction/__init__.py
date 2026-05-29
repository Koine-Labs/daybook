# apps/inference/prediction/__init__.py
"""L4 prediction layer — forecasts future per-axis state from the BeliefState.

Wraps the JEPA-family destination (commitment #16) behind a predict(axis,
horizon, action) seam (#15/#16). v1 ships honest placeholder predictors; the
PREDICTION_OFFLINE sentinel mirrors L3's OFFLINE idea (returned, never raised).
"""
from __future__ import annotations

from .interface import PREDICTION_OFFLINE, Predictor, predict

__all__ = ["PREDICTION_OFFLINE", "Predictor", "predict"]
