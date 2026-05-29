# apps/inference/prediction/predictors/sleep_classifier.py
"""L4 REM nowcast — the REAL trained binary-REM XGBoost wrapped as a predictor.

This is the first NON-placeholder L4 predictor: a stand-alone per-axis predictor
(commitment #16) for axis "rem". It is FEATURE-BASED — it consumes the 24 pure-
biometric features that L2 derives per 30s epoch (the exact ordered set the model
was trained on, frozen in production_binary_rem.meta.json), NOT an L3 BeliefState.

It is a NOWCAST, not a forecast: horizon_seconds=0. The output is the model's
estimate of P(REM) for the *current* epoch given the trailing 5-minute context
window — the same quantity the v0 RealtimeClassifier.predict_at produced. Calling
it a forecast would be dishonest, so the horizon is explicitly zero and the
provenance stays "placeholder" (no action-conditioning, no causal world model yet
per #15/#16). The probability itself is the real model output — never fabricated.

Inference is recovered faithfully from v0 realtime.py: load the XGBoost model +
sidecar, order the 24 features exactly per feature_cols, missing features become
NaN (XGBoost handles NaN natively), predict_proba column 1 is P(REM), and the
chosen threshold (0.23) decides the binary REM call. Feature *math* is owned by
classifier/features.py upstream — this module never recomputes features.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import xgboost as xgb

from core.protocol.payloads import Prediction
from fusion.belief_state import AxisEstimate

REM_AXIS = "rem"
MODEL_ID = "production_binary_rem"
# A nowcast: P(REM) for the current epoch, not a future forecast (honest #16).
HORIZON_SECONDS = 0

_MODELS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "classifier" / "models"
)
_META_NAME = "production_binary_rem.meta.json"


class SleepClassifierPredictor:
    """Wraps the frozen binary-REM XGBoost as a feature-based REM nowcaster.

    Conforms to the L4 Predictor protocol (so registry.register works) AND
    exposes score_features() for the feature_participant, which feeds the 24
    features straight from an L2 biometric FeatureSnapshot rather than an
    AxisEstimate.
    """

    model_id: str = MODEL_ID

    def __init__(self, model_dir: Path | None = None) -> None:
        self._model_dir = model_dir or _MODELS_DIR
        self._model: xgb.XGBClassifier | None = None
        self._feature_cols: list[str] | None = None
        self._threshold: float | None = None

    # ---- lazy model load (mirrors v0 RealtimeClassifier.load) -------------

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        meta_path = self._model_dir / _META_NAME
        meta = json.loads(meta_path.read_text())
        model = xgb.XGBClassifier()
        model.load_model(str(self._model_dir / meta["model_path"]))
        self._model = model
        self._feature_cols = list(meta["feature_cols"])
        self._threshold = float(meta["chosen_threshold"])

    @property
    def feature_cols(self) -> list[str]:
        self._ensure_loaded()
        assert self._feature_cols is not None
        return self._feature_cols

    @property
    def threshold(self) -> float:
        self._ensure_loaded()
        assert self._threshold is not None
        return self._threshold

    # ---- core scoring (recovers v0 predict_proba + ordering) --------------

    def score_features(self, features: dict[str, Any]) -> float:
        """Return P(REM) for one epoch's 24-feature dict.

        Features are ordered exactly per feature_cols; any absent feature is
        NaN (XGBoost handles missing natively, as v0 did). Returns column-1
        probability — the same value v0 RealtimeClassifier reported.
        """
        self._ensure_loaded()
        assert self._model is not None and self._feature_cols is not None
        x_row = np.array(
            [[_as_float(features.get(c)) for c in self._feature_cols]],
            dtype=np.float64,
        )
        return float(self._model.predict_proba(x_row)[0, 1])

    def is_rem(self, proba: float) -> bool:
        """Apply the frozen decision threshold (0.23)."""
        return proba >= self.threshold

    def predict_rem(
        self,
        *,
        user_id: str,
        features: dict[str, Any],
        now: datetime | None = None,
        i_model_id: str | None = None,
        action: dict[str, Any] | None = None,
    ) -> Prediction:
        """Score a 24-feature dict into a well-formed "rem" Prediction (nowcast)."""
        if now is None:
            now = datetime.now(timezone.utc)
        proba = self.score_features(features)
        return Prediction(
            user_id=user_id,
            axis=REM_AXIS,
            made_at=now,
            horizon_seconds=HORIZON_SECONDS,
            distribution={"rem": proba, "non_rem": 1.0 - proba},
            model_id=self.model_id,
            confidence=proba,
            action=action,
            provenance="placeholder",
            cold_start=False,
            i_model_id=i_model_id,
        )

    # ---- Predictor-protocol entry point -----------------------------------

    def predict(
        self,
        *,
        axis: str,
        estimate: AxisEstimate,
        horizon_seconds: int,
        action: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> Prediction:
        """Protocol path: pull the 24 features out of the AxisEstimate value.

        The canonical live path is the feature_participant calling predict_rem
        with an L2 biometric FeatureSnapshot. This method exists so the predictor
        is registerable under (axis, meta_context) and usable from a BeliefState
        whose axis estimate carries the feature vector under value["features"].
        horizon_seconds is ignored: this is a current-epoch nowcast.
        """
        features = _features_from_estimate(estimate)
        return self.predict_rem(
            user_id=getattr(estimate, "user_id", "unknown"),
            features=features,
            now=now,
            i_model_id=estimate.i_model_id,
            action=action,
        )


def predict_from_features(
    predictor: SleepClassifierPredictor,
    *,
    user_id: str,
    features: dict[str, Any],
    now: datetime | None = None,
    i_model_id: str | None = None,
    action: dict[str, Any] | None = None,
) -> Prediction:
    """Module-level convenience matching the feature-based call shape."""
    return predictor.predict_rem(
        user_id=user_id,
        features=features,
        now=now,
        i_model_id=i_model_id,
        action=action,
    )


def _features_from_estimate(estimate: AxisEstimate) -> dict[str, Any]:
    """Extract the feature dict an AxisEstimate carries (value or value.features)."""
    value = getattr(estimate, "value", None)
    if isinstance(value, dict):
        nested = value.get("features")
        if isinstance(nested, dict):
            return nested
        return value
    return {}


def _as_float(v: Any) -> float:
    """Coerce a feature value to float; None / unparseable -> NaN (model-native)."""
    if v is None:
        return float("nan")
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


# Shared instance so the registry and the participant load the model once.
DEFAULT_PREDICTOR = SleepClassifierPredictor()
