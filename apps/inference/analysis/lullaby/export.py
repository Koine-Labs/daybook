"""
Model serialization and export for Lullaby sleep classifier.

Saves trained models as:
- ``model.joblib`` — Serialized XGBClassifier for Python server deployment.
- ``config.json`` — Version, hyperparameters, metrics, and feature config.
- ``feature_names.json`` — Ordered feature name list.
- ``model.mlmodel`` — CoreML model for iOS/watchOS on-device fallback.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from xgboost import XGBClassifier

from lullaby.model import TrainedModel, XGBConfig
from lullaby.evaluation import ClassificationMetrics


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

class ModelArtifact:
    """Loaded model artifact from disk."""

    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.model_path = model_dir / "model.joblib"
        self.config_path = model_dir / "config.json"
        self.features_path = model_dir / "feature_names.json"

    @property
    def exists(self) -> bool:
        return self.model_path.exists() and self.config_path.exists()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_model(
    model: TrainedModel,
    output_dir: str | Path,
    version: str = "0.1.0",
    metrics: Optional[ClassificationMetrics] = None,
) -> Path:
    """Save a trained model to disk.

    Creates the output directory and writes:
    - ``model.joblib`` — The serialized XGBClassifier.
    - ``config.json`` — Version, hyperparameters, metrics summary.
    - ``feature_names.json`` — Ordered feature name list.

    Args:
        model: Trained model to save.
        output_dir: Directory to write files to.
        version: Model version string.
        metrics: Optional metrics to include in config.

    Returns:
        Path to the output directory.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save XGBClassifier
    joblib.dump(model.model, output_dir / "model.joblib")

    # Save feature names
    with open(output_dir / "feature_names.json", "w") as f:
        json.dump(model.feature_names, f, indent=2)

    # Build config
    config_dict = {
        "version": version,
        "binary": model.binary,
        "label_map": {str(k): v for k, v in model.label_map.items()},
        "hyperparameters": asdict(model.config),
        "n_features": len(model.feature_names),
    }

    if metrics is not None:
        config_dict["metrics"] = {
            "accuracy": metrics.accuracy,
            "macro_f1": metrics.macro_f1,
            "weighted_f1": metrics.weighted_f1,
            "rem_precision": metrics.rem_precision,
            "rem_recall": metrics.rem_recall,
            "rem_f1": metrics.rem_f1,
            "cohens_kappa": metrics.cohens_kappa,
        }

    with open(output_dir / "config.json", "w") as f:
        json.dump(config_dict, f, indent=2)

    return output_dir


def load_model(model_dir: str | Path) -> tuple[TrainedModel, ModelArtifact]:
    """Load a saved model from disk.

    Args:
        model_dir: Directory containing model files.

    Returns:
        Tuple of (TrainedModel, ModelArtifact).

    Raises:
        FileNotFoundError: If required files are missing.
    """
    model_dir = Path(model_dir)
    artifact = ModelArtifact(model_dir)

    if not artifact.model_path.exists():
        raise FileNotFoundError(f"Model file not found: {artifact.model_path}")
    if not artifact.config_path.exists():
        raise FileNotFoundError(f"Config file not found: {artifact.config_path}")

    # Load classifier
    clf = joblib.load(artifact.model_path)

    # Load config
    with open(artifact.config_path, "r") as f:
        config_dict = json.load(f)

    # Load feature names
    feature_names = []
    if artifact.features_path.exists():
        with open(artifact.features_path, "r") as f:
            feature_names = json.load(f)

    # Reconstruct XGBConfig
    hp = config_dict.get("hyperparameters", {})
    config = XGBConfig(
        n_estimators=hp.get("n_estimators", 300),
        max_depth=hp.get("max_depth", 6),
        learning_rate=hp.get("learning_rate", 0.1),
        subsample=hp.get("subsample", 0.8),
        colsample_bytree=hp.get("colsample_bytree", 0.8),
        min_child_weight=hp.get("min_child_weight", 3),
        gamma=hp.get("gamma", 0.1),
        reg_alpha=hp.get("reg_alpha", 0.1),
        reg_lambda=hp.get("reg_lambda", 1.0),
        random_state=hp.get("random_state", 42),
        n_jobs=hp.get("n_jobs", -1),
        verbosity=hp.get("verbosity", 0),
    )

    # Reconstruct label map
    label_map_raw = config_dict.get("label_map", {})
    label_map = {int(k): v for k, v in label_map_raw.items()}

    trained = TrainedModel(
        model=clf,
        config=config,
        feature_names=feature_names,
        label_map=label_map,
        binary=config_dict.get("binary", False),
    )

    return trained, artifact


def export_coreml(
    model: TrainedModel,
    output_path: str | Path,
    model_description: str = "Lullaby Sleep Stage Classifier",
) -> Path:
    """Export model to CoreML format for iOS/watchOS on-device inference.

    Args:
        model: Trained XGBoost model to export.
        output_path: Path to write the .mlmodel file.
        model_description: Human-readable model description.

    Returns:
        Path to the saved .mlmodel file.
    """
    import coremltools as ct

    output_path = Path(output_path)

    # Convert XGBoost → CoreML via coremltools
    coreml_model = ct.converters.xgboost.convert(
        model.model,
        feature_names=model.feature_names,
        mode="classifier" if not model.binary else "classifier",
    )

    # Set metadata
    coreml_model.short_description = model_description
    coreml_model.author = "Lullaby"
    coreml_model.version = "0.1.0"

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    coreml_model.save(str(output_path))

    return output_path
