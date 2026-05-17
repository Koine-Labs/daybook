"""
XGBoost model training for Lullaby sleep stage classification.

Supports both 5-class (awake, REM, core, deep, inBed) and binary
(REM vs rest) classification with class-imbalance handling,
leave-one-session-out cross-validation, and random hyperparameter search.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from lullaby.pipeline import (
    ClassificationDataset,
    TrainTestSplit,
    get_leave_one_out_splits,
    make_binary_labels,
    STAGE_TO_INT,
    INT_TO_STAGE,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class XGBConfig:
    """Hyperparameters for XGBoost training."""

    n_estimators: int = 300
    max_depth: int = 6
    learning_rate: float = 0.1
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    min_child_weight: int = 3
    gamma: float = 0.1
    reg_alpha: float = 0.1
    reg_lambda: float = 1.0
    random_state: int = 42
    n_jobs: int = -1
    verbosity: int = 0


DEFAULT_CONFIG = XGBConfig()


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class TrainedModel:
    """A fitted XGBoost model with metadata."""

    model: XGBClassifier
    config: XGBConfig
    feature_names: list[str]
    label_map: dict[int, str]      # int → stage name
    binary: bool                    # True if binary REM classifier
    training_history: dict = field(default_factory=dict)


@dataclass
class CVResult:
    """Cross-validation results."""

    fold_metrics: list[dict]        # per-fold metric dicts
    mean_metrics: dict              # mean across folds
    std_metrics: dict               # std across folds
    fold_models: list[TrainedModel]
    best_fold_index: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def train_multiclass(
    dataset: ClassificationDataset,
    config: Optional[XGBConfig] = None,
) -> TrainedModel:
    """Train a 5-class sleep stage classifier.

    Uses ``multi:softprob`` objective with balanced sample weights to
    handle class imbalance (REM and deep sleep are underrepresented).

    Args:
        dataset: Prepared classification dataset.
        config: XGBoost hyperparameters (None → defaults).

    Returns:
        A ``TrainedModel`` wrapping the fitted XGBClassifier.
    """
    if config is None:
        config = DEFAULT_CONFIG

    clf = XGBClassifier(
        objective="multi:softprob",
        num_class=len(dataset.stage_labels),
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        learning_rate=config.learning_rate,
        subsample=config.subsample,
        colsample_bytree=config.colsample_bytree,
        min_child_weight=config.min_child_weight,
        gamma=config.gamma,
        reg_alpha=config.reg_alpha,
        reg_lambda=config.reg_lambda,
        random_state=config.random_state,
        n_jobs=config.n_jobs,
        verbosity=config.verbosity,
        use_label_encoder=False,
        eval_metric="mlogloss",
    )

    sample_weights = compute_sample_weight("balanced", dataset.y)
    clf.fit(dataset.X, dataset.y, sample_weight=sample_weights)

    return TrainedModel(
        model=clf,
        config=config,
        feature_names=dataset.feature_names,
        label_map=INT_TO_STAGE,
        binary=False,
    )


def train_binary_rem(
    dataset: ClassificationDataset,
    config: Optional[XGBConfig] = None,
) -> TrainedModel:
    """Train a binary REM-vs-rest classifier.

    Uses ``binary:logistic`` with automatic ``scale_pos_weight`` to
    account for REM class imbalance.

    Args:
        dataset: Prepared classification dataset (multi-class labels).
        config: XGBoost hyperparameters (None → defaults).

    Returns:
        A ``TrainedModel`` with binary labels.
    """
    if config is None:
        config = DEFAULT_CONFIG

    y_binary = make_binary_labels(dataset.y, positive_class="remSleep")

    n_positive = int(y_binary.sum())
    n_negative = len(y_binary) - n_positive
    scale_pos_weight = n_negative / max(n_positive, 1)

    clf = XGBClassifier(
        objective="binary:logistic",
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        learning_rate=config.learning_rate,
        subsample=config.subsample,
        colsample_bytree=config.colsample_bytree,
        min_child_weight=config.min_child_weight,
        gamma=config.gamma,
        reg_alpha=config.reg_alpha,
        reg_lambda=config.reg_lambda,
        scale_pos_weight=scale_pos_weight,
        random_state=config.random_state,
        n_jobs=config.n_jobs,
        verbosity=config.verbosity,
        use_label_encoder=False,
        eval_metric="logloss",
    )

    clf.fit(dataset.X, y_binary)

    return TrainedModel(
        model=clf,
        config=config,
        feature_names=dataset.feature_names,
        label_map={0: "non-REM", 1: "REM"},
        binary=True,
    )


def cross_validate(
    dataset: ClassificationDataset,
    config: Optional[XGBConfig] = None,
    binary: bool = False,
) -> CVResult:
    """Leave-one-session-out cross-validation.

    Trains one model per fold (holding out one session) and computes
    per-fold accuracy and REM F1 metrics.

    Args:
        dataset: Full classification dataset.
        config: XGBoost hyperparameters (None → defaults).
        binary: If True, train binary REM classifier per fold.

    Returns:
        A ``CVResult`` with per-fold and aggregate metrics.
    """
    if config is None:
        config = DEFAULT_CONFIG

    splits = get_leave_one_out_splits(dataset)
    fold_metrics: list[dict] = []
    fold_models: list[TrainedModel] = []

    for split in splits:
        if binary:
            trained = train_binary_rem(split.train, config)
            y_test = make_binary_labels(split.test.y)
        else:
            trained = train_multiclass(split.train, config)
            y_test = split.test.y

        y_pred = trained.model.predict(split.test.X)

        # Compute basic metrics
        accuracy = float(np.mean(y_pred == y_test))

        # REM-specific metrics
        if binary:
            rem_true = y_test == 1
            rem_pred = y_pred == 1
        else:
            rem_int = STAGE_TO_INT["remSleep"]
            rem_true = y_test == rem_int
            rem_pred = y_pred == rem_int

        tp = int(np.sum(rem_true & rem_pred))
        fp = int(np.sum(~rem_true & rem_pred))
        fn = int(np.sum(rem_true & ~rem_pred))

        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-10)

        metrics = {
            "accuracy": accuracy,
            "rem_precision": precision,
            "rem_recall": recall,
            "rem_f1": f1,
            "test_session": split.test_session_ids[0],
            "n_test_epochs": len(y_test),
        }
        fold_metrics.append(metrics)
        fold_models.append(trained)

    # Aggregate
    metric_keys = ["accuracy", "rem_precision", "rem_recall", "rem_f1"]
    mean_metrics = {k: float(np.mean([m[k] for m in fold_metrics])) for k in metric_keys}
    std_metrics = {k: float(np.std([m[k] for m in fold_metrics])) for k in metric_keys}

    # Best fold by REM F1
    best_idx = int(np.argmax([m["rem_f1"] for m in fold_metrics]))

    return CVResult(
        fold_metrics=fold_metrics,
        mean_metrics=mean_metrics,
        std_metrics=std_metrics,
        fold_models=fold_models,
        best_fold_index=best_idx,
    )


def tune_hyperparameters(
    dataset: ClassificationDataset,
    n_iter: int = 20,
    metric: str = "rem_f1",
    seed: int = 42,
    binary: bool = False,
) -> tuple[XGBConfig, CVResult]:
    """Random hyperparameter search with cross-validation.

    Samples *n_iter* random configurations and evaluates each with
    leave-one-session-out CV.  Returns the best config and its results.

    Args:
        dataset: Full classification dataset.
        n_iter: Number of random configurations to try.
        metric: CV metric to optimize (key in ``CVResult.mean_metrics``).
        seed: Random seed.
        binary: If True, tune binary REM classifier.

    Returns:
        Tuple of (best_config, best_cv_result).
    """
    rng = np.random.default_rng(seed)

    # Parameter grid
    param_grid = {
        "n_estimators": [100, 200, 300, 500],
        "max_depth": [3, 4, 5, 6, 8],
        "learning_rate": [0.01, 0.05, 0.1, 0.2],
        "subsample": [0.6, 0.7, 0.8, 0.9, 1.0],
        "colsample_bytree": [0.6, 0.7, 0.8, 0.9, 1.0],
        "min_child_weight": [1, 3, 5, 7],
        "gamma": [0.0, 0.1, 0.2, 0.5],
        "reg_alpha": [0.0, 0.01, 0.1, 1.0],
        "reg_lambda": [0.5, 1.0, 2.0, 5.0],
    }

    best_score = -1.0
    best_config: Optional[XGBConfig] = None
    best_result: Optional[CVResult] = None

    for _ in range(n_iter):
        config = XGBConfig(
            n_estimators=int(rng.choice(param_grid["n_estimators"])),
            max_depth=int(rng.choice(param_grid["max_depth"])),
            learning_rate=float(rng.choice(param_grid["learning_rate"])),
            subsample=float(rng.choice(param_grid["subsample"])),
            colsample_bytree=float(rng.choice(param_grid["colsample_bytree"])),
            min_child_weight=int(rng.choice(param_grid["min_child_weight"])),
            gamma=float(rng.choice(param_grid["gamma"])),
            reg_alpha=float(rng.choice(param_grid["reg_alpha"])),
            reg_lambda=float(rng.choice(param_grid["reg_lambda"])),
            random_state=42,
            n_jobs=-1,
            verbosity=0,
        )

        cv_result = cross_validate(dataset, config=config, binary=binary)
        score = cv_result.mean_metrics.get(metric, 0.0)

        if score > best_score:
            best_score = score
            best_config = config
            best_result = cv_result

    assert best_config is not None
    assert best_result is not None
    return best_config, best_result
