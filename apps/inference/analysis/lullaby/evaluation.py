"""
Model evaluation for Lullaby sleep stage classification.

Computes classification metrics, generates confusion matrices,
hypnogram comparisons, SHAP feature importance plots, and checks
Phase 2 success criteria (REM F1 ≥ 0.65).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from lullaby.model import TrainedModel, CVResult
from lullaby.pipeline import (
    ClassificationDataset,
    STAGE_TO_INT,
    INT_TO_STAGE,
    STAGE_LABELS,
    make_binary_labels,
)
from lullaby.visualization import STAGE_COLORS, STAGE_ORDER


# ---------------------------------------------------------------------------
# Metrics containers
# ---------------------------------------------------------------------------

@dataclass
class ClassificationMetrics:
    """Full evaluation metrics for a trained model."""

    accuracy: float
    per_class_precision: dict[str, float]
    per_class_recall: dict[str, float]
    per_class_f1: dict[str, float]
    macro_f1: float
    weighted_f1: float
    confusion: np.ndarray                # (n_classes, n_classes)
    confusion_labels: list[str]
    cohens_kappa: float

    # REM-specific
    rem_precision: float
    rem_recall: float
    rem_f1: float
    rem_onset_latency: Optional[float]   # mean epochs delay (None if no REM bouts)


@dataclass
class SuccessCriteria:
    """Phase 2 gate check results."""

    rem_precision_target: float = 0.70
    rem_recall_target: float = 0.60
    rem_f1_target: float = 0.65

    rem_precision_met: bool = False
    rem_recall_met: bool = False
    rem_f1_met: bool = False

    @property
    def passed(self) -> bool:
        return self.rem_precision_met and self.rem_recall_met and self.rem_f1_met


# ---------------------------------------------------------------------------
# Public API — metrics
# ---------------------------------------------------------------------------

def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    label_map: Optional[dict[int, str]] = None,
    binary: bool = False,
) -> ClassificationMetrics:
    """Compute full classification metrics.

    Args:
        y_true: Ground truth labels (integer-encoded).
        y_pred: Predicted labels (integer-encoded).
        label_map: Mapping from int → stage name.  Defaults to INT_TO_STAGE.
        binary: If True, compute binary REM metrics (1 = REM, 0 = rest).

    Returns:
        A ``ClassificationMetrics`` with all evaluation measures.
    """
    if label_map is None:
        label_map = INT_TO_STAGE if not binary else {0: "non-REM", 1: "REM"}

    # Determine present classes
    present_classes = sorted(set(y_true) | set(y_pred))
    class_names = [label_map.get(c, str(c)) for c in present_classes]

    accuracy = float(accuracy_score(y_true, y_pred))

    # Per-class metrics
    per_class_p: dict[str, float] = {}
    per_class_r: dict[str, float] = {}
    per_class_f: dict[str, float] = {}

    for cls_int, cls_name in zip(present_classes, class_names):
        cls_true = (y_true == cls_int).astype(int)
        cls_pred = (y_pred == cls_int).astype(int)
        tp = int(np.sum(cls_true & cls_pred))
        fp = int(np.sum((1 - cls_true) & cls_pred))
        fn = int(np.sum(cls_true & (1 - cls_pred)))
        per_class_p[cls_name] = tp / max(tp + fp, 1)
        per_class_r[cls_name] = tp / max(tp + fn, 1)
        p, r = per_class_p[cls_name], per_class_r[cls_name]
        per_class_f[cls_name] = 2 * p * r / max(p + r, 1e-10)

    macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(y_true, y_pred, average="weighted", zero_division=0))

    cm = confusion_matrix(y_true, y_pred, labels=present_classes)
    kappa = float(cohen_kappa_score(y_true, y_pred))

    # REM-specific
    if binary:
        rem_p = per_class_p.get("REM", 0.0)
        rem_r = per_class_r.get("REM", 0.0)
        rem_f = per_class_f.get("REM", 0.0)
    else:
        rem_name = "remSleep"
        rem_p = per_class_p.get(rem_name, 0.0)
        rem_r = per_class_r.get(rem_name, 0.0)
        rem_f = per_class_f.get(rem_name, 0.0)

    return ClassificationMetrics(
        accuracy=accuracy,
        per_class_precision=per_class_p,
        per_class_recall=per_class_r,
        per_class_f1=per_class_f,
        macro_f1=macro_f1,
        weighted_f1=weighted_f1,
        confusion=cm,
        confusion_labels=class_names,
        cohens_kappa=kappa,
        rem_precision=rem_p,
        rem_recall=rem_r,
        rem_f1=rem_f,
        rem_onset_latency=None,  # Computed separately
    )


def compute_rem_onset_latency(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    rem_label: int = 1,
) -> Optional[float]:
    """Compute mean REM onset detection latency in epochs.

    For each contiguous REM bout in *y_true*, find the first epoch
    where *y_pred* also predicts REM.  The latency is the offset
    from the bout start.  Undetected bouts count as ``bout_length``.

    Args:
        y_true: Ground truth labels.
        y_pred: Predicted labels.
        rem_label: Integer label for REM class.

    Returns:
        Mean latency in epochs, or None if no REM bouts exist.
    """
    bouts = _find_contiguous_bouts(y_true, rem_label)
    if not bouts:
        return None

    latencies: list[int] = []
    for start, end in bouts:
        bout_preds = y_pred[start:end]
        rem_indices = np.where(bout_preds == rem_label)[0]
        if len(rem_indices) > 0:
            latencies.append(int(rem_indices[0]))
        else:
            # Undetected — penalty = bout length
            latencies.append(end - start)

    return float(np.mean(latencies))


def check_success_criteria(
    metrics: ClassificationMetrics,
    precision_target: float = 0.70,
    recall_target: float = 0.60,
    f1_target: float = 0.65,
) -> SuccessCriteria:
    """Check Phase 2 success criteria against computed metrics.

    Args:
        metrics: Computed classification metrics.
        precision_target: Minimum REM precision.
        recall_target: Minimum REM recall.
        f1_target: Minimum REM F1.

    Returns:
        A ``SuccessCriteria`` with pass/fail for each metric.
    """
    return SuccessCriteria(
        rem_precision_target=precision_target,
        rem_recall_target=recall_target,
        rem_f1_target=f1_target,
        rem_precision_met=metrics.rem_precision >= precision_target,
        rem_recall_met=metrics.rem_recall >= recall_target,
        rem_f1_met=metrics.rem_f1 >= f1_target,
    )


def predict(
    model: TrainedModel,
    dataset: ClassificationDataset,
) -> np.ndarray:
    """Generate predictions, handling multiclass vs binary transparently.

    Args:
        model: A trained model.
        dataset: Dataset to predict on.

    Returns:
        Integer-encoded predictions.
    """
    if model.binary:
        y_pred = model.model.predict(dataset.X)
    else:
        y_pred = model.model.predict(dataset.X)
    return y_pred.astype(np.int64)


# ---------------------------------------------------------------------------
# Public API — visualization
# ---------------------------------------------------------------------------

def plot_confusion_matrix(
    metrics: ClassificationMetrics,
    figsize: tuple[float, float] = (8, 6),
    normalize: bool = True,
) -> plt.Figure:
    """Plot confusion matrix as a heatmap.

    Args:
        metrics: Computed classification metrics.
        figsize: Figure dimensions.
        normalize: If True, show row-normalized percentages.

    Returns:
        matplotlib Figure.
    """
    fig, ax = plt.subplots(figsize=figsize)

    if normalize:
        cm = metrics.confusion.astype(float)
        row_sums = cm.sum(axis=1, keepdims=True)
        row_sums = np.where(row_sums == 0, 1, row_sums)
        cm = cm / row_sums
        fmt = ".2f"
    else:
        cm = metrics.confusion.astype(int)
        fmt = "d"

    sns.heatmap(
        cm,
        annot=True,
        fmt=fmt,
        cmap="Blues",
        xticklabels=metrics.confusion_labels,
        yticklabels=metrics.confusion_labels,
        ax=ax,
    )
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Confusion Matrix" + (" (Normalized)" if normalize else ""))
    fig.tight_layout()
    return fig


def plot_hypnogram_comparison(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    label_map: Optional[dict[int, str]] = None,
    figsize: tuple[float, float] = (16, 4),
) -> plt.Figure:
    """Plot ground truth vs predicted hypnogram as a dual timeline.

    Args:
        y_true: Ground truth labels (integer-encoded).
        y_pred: Predicted labels (integer-encoded).
        label_map: Mapping from int → stage name.
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    if label_map is None:
        label_map = INT_TO_STAGE

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, sharex=True)

    # Map int labels back to stage names for y-axis ordering
    stage_to_y = {stage: i for i, stage in enumerate(STAGE_ORDER) if stage in label_map.values()}

    for ax, y_data, title in [(ax1, y_true, "Ground Truth"), (ax2, y_pred, "Predicted")]:
        y_positions = []
        colors = []
        for val in y_data:
            name = label_map.get(int(val), "unknown")
            y_positions.append(stage_to_y.get(name, -1))
            colors.append(STAGE_COLORS.get(name, "#BDC3C7"))

        epochs = np.arange(len(y_data))
        ax.scatter(epochs, y_positions, c=colors, s=4, marker="s")
        ax.set_yticks(list(stage_to_y.values()))
        ax.set_yticklabels(list(stage_to_y.keys()))
        ax.set_title(title)
        ax.set_ylabel("Stage")

    ax2.set_xlabel("Epoch")
    fig.tight_layout()
    return fig


def plot_feature_importance(
    model: TrainedModel,
    max_features: int = 20,
    figsize: tuple[float, float] = (10, 8),
) -> plt.Figure:
    """Plot XGBoost feature importance as a horizontal bar chart.

    Args:
        model: Trained XGBoost model.
        max_features: Maximum number of features to display.
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    importance = model.model.feature_importances_
    indices = np.argsort(importance)[-max_features:]

    fig, ax = plt.subplots(figsize=figsize)
    names = [model.feature_names[i] for i in indices]
    values = importance[indices]

    ax.barh(range(len(indices)), values, color="#3498DB")
    ax.set_yticks(range(len(indices)))
    ax.set_yticklabels(names)
    ax.set_xlabel("Importance (gain)")
    ax.set_title("Feature Importance")
    fig.tight_layout()
    return fig


def plot_shap_summary(
    model: TrainedModel,
    dataset: ClassificationDataset,
    max_samples: int = 500,
    figsize: tuple[float, float] = (10, 8),
) -> plt.Figure:
    """Plot SHAP beeswarm summary for the model.

    Uses TreeExplainer for efficient computation on XGBoost models.

    Args:
        model: Trained XGBoost model.
        dataset: Dataset to explain (subsampled if needed).
        max_samples: Maximum samples for SHAP computation.
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    import shap

    n = min(max_samples, len(dataset.X))
    X_sample = dataset.X[:n]

    explainer = shap.TreeExplainer(model.model)
    shap_values = explainer.shap_values(X_sample)

    fig, ax = plt.subplots(figsize=figsize)

    # Handle different SHAP output shapes:
    # - list of arrays (older shap): one (n_samples, n_features) per class
    # - 3D array (newer shap): (n_samples, n_features, n_classes)
    # - 2D array (binary): (n_samples, n_features)
    if isinstance(shap_values, list):
        mean_abs = np.mean([np.abs(sv) for sv in shap_values], axis=0)
    elif shap_values.ndim == 3:
        mean_abs = np.mean(np.abs(shap_values), axis=2)
    else:
        mean_abs = np.abs(shap_values)

    feature_importance = mean_abs.mean(axis=0)
    indices = np.argsort(feature_importance)[-20:]

    ax.barh(
        range(len(indices)),
        feature_importance[indices],
        color="#E74C3C",
    )
    ax.set_yticks(range(len(indices)))
    ax.set_yticklabels([dataset.feature_names[i] for i in indices])
    ax.set_xlabel("Mean |SHAP value|")
    ax.set_title("SHAP Feature Importance")
    fig.tight_layout()
    return fig


def plot_cv_results(
    cv_result: CVResult,
    figsize: tuple[float, float] = (12, 5),
) -> plt.Figure:
    """Plot per-fold CV metrics as a grouped bar chart.

    Args:
        cv_result: Cross-validation results.
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    fig, ax = plt.subplots(figsize=figsize)

    metrics_to_plot = ["accuracy", "rem_precision", "rem_recall", "rem_f1"]
    n_folds = len(cv_result.fold_metrics)
    x = np.arange(n_folds)
    width = 0.2

    for i, metric_name in enumerate(metrics_to_plot):
        values = [m[metric_name] for m in cv_result.fold_metrics]
        ax.bar(x + i * width, values, width, label=metric_name)

    ax.set_xlabel("Fold")
    ax.set_ylabel("Score")
    ax.set_title("Cross-Validation Results (per fold)")
    ax.set_xticks(x + width * 1.5)
    ax.set_xticklabels([f"Fold {i}" for i in range(n_folds)])
    ax.legend()
    ax.set_ylim(0, 1.05)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Public API — reporting
# ---------------------------------------------------------------------------

def print_metrics_report(
    metrics: ClassificationMetrics,
    criteria: Optional[SuccessCriteria] = None,
) -> str:
    """Format a text report of classification metrics.

    Args:
        metrics: Computed classification metrics.
        criteria: Optional success criteria for pass/fail annotation.

    Returns:
        Formatted report string (also printed to stdout).
    """
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("SLEEP STAGE CLASSIFICATION REPORT")
    lines.append("=" * 60)
    lines.append(f"  Overall Accuracy:  {metrics.accuracy:.3f}")
    lines.append(f"  Macro F1:          {metrics.macro_f1:.3f}")
    lines.append(f"  Weighted F1:       {metrics.weighted_f1:.3f}")
    lines.append(f"  Cohen's Kappa:     {metrics.cohens_kappa:.3f}")
    lines.append("")
    lines.append("Per-class F1:")
    for cls_name in metrics.per_class_f1:
        p = metrics.per_class_precision.get(cls_name, 0)
        r = metrics.per_class_recall.get(cls_name, 0)
        f = metrics.per_class_f1.get(cls_name, 0)
        lines.append(f"  {cls_name:15s}  P={p:.3f}  R={r:.3f}  F1={f:.3f}")

    lines.append("")
    lines.append("REM-Specific Metrics:")
    lines.append(f"  Precision: {metrics.rem_precision:.3f}")
    lines.append(f"  Recall:    {metrics.rem_recall:.3f}")
    lines.append(f"  F1:        {metrics.rem_f1:.3f}")
    if metrics.rem_onset_latency is not None:
        lines.append(f"  Onset Latency: {metrics.rem_onset_latency:.1f} epochs")

    if criteria is not None:
        lines.append("")
        lines.append("Phase 2 Success Criteria:")
        _check = lambda met, target: "PASS" if met else "FAIL"
        lines.append(f"  REM Precision >= {criteria.rem_precision_target:.2f}: "
                      f"{_check(criteria.rem_precision_met, criteria.rem_precision_target)}")
        lines.append(f"  REM Recall    >= {criteria.rem_recall_target:.2f}: "
                      f"{_check(criteria.rem_recall_met, criteria.rem_recall_target)}")
        lines.append(f"  REM F1        >= {criteria.rem_f1_target:.2f}: "
                      f"{_check(criteria.rem_f1_met, criteria.rem_f1_target)}")
        lines.append(f"  Overall: {'PASSED' if criteria.passed else 'FAILED'}")

    lines.append("=" * 60)

    report = "\n".join(lines)
    print(report)
    return report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_contiguous_bouts(
    y: np.ndarray,
    target_label: int,
) -> list[tuple[int, int]]:
    """Find contiguous bouts of *target_label* in *y*.

    Returns:
        List of (start_index, end_index) tuples.  End is exclusive.
    """
    bouts: list[tuple[int, int]] = []
    in_bout = False
    start = 0

    for i, val in enumerate(y):
        if val == target_label and not in_bout:
            in_bout = True
            start = i
        elif val != target_label and in_bout:
            in_bout = False
            bouts.append((start, i))

    if in_bout:
        bouts.append((start, len(y)))

    return bouts
