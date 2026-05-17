"""XGBoost sleep stage classifier wrapper."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

logger = logging.getLogger(__name__)

STAGE_LABELS = ["awake", "remSleep", "coreLight", "deepSleep", "inBed"]


@dataclass
class PredictionResult:
    stage: str
    confidence: float
    probabilities: dict[str, float]


class Classifier:
    def __init__(self, model_dir: str | Path) -> None:
        model_dir = Path(model_dir)
        self.model = joblib.load(model_dir / "model.joblib")
        with open(model_dir / "feature_names.json") as f:
            self.feature_names: list[str] = json.load(f)
        config_path = model_dir / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
            label_map = config.get("label_map", {})
            self._labels = [label_map.get(str(i), STAGE_LABELS[i]) for i in range(len(STAGE_LABELS))]
        else:
            self._labels = STAGE_LABELS
        logger.info(f"Loaded model with {len(self.feature_names)} features")

    def predict(self, features: dict[str, float]) -> PredictionResult:
        vector = []
        for name in self.feature_names:
            value = features.get(name, float("nan"))
            if name not in features:
                logger.warning(f"Missing feature: {name}, using NaN")
            vector.append(value)
        X = np.array([vector], dtype=np.float64)
        probas = self.model.predict_proba(X)[0]
        pred_idx = int(np.argmax(probas))
        return PredictionResult(
            stage=self._labels[pred_idx],
            confidence=float(probas[pred_idx]),
            probabilities={label: float(p) for label, p in zip(self._labels, probas)},
        )
