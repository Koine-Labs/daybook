from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

try:
    from .baselines import HRThresholdBaseline, MajorityBaseline, RandomBaseline
    from .train import FEATURES_CACHE, INT_TO_STAGE, STAGE_TO_INT
except ImportError:
    from baselines import HRThresholdBaseline, MajorityBaseline, RandomBaseline  # type: ignore[no-redef]
    from train import FEATURES_CACHE, INT_TO_STAGE, STAGE_TO_INT  # type: ignore[no-redef]

CLASS_NAMES = ["AWAKE", "CORE", "DEEP", "REM"]


def _safe_metric(fn, *a, **kw) -> float:
    try:
        return float(fn(*a, **kw))
    except Exception:
        return float("nan")


def _binary_session_f1(df: pd.DataFrame) -> float:
    return _safe_metric(f1_score, df["y_true"], df["y_pred"], zero_division=0)


def _multiclass_session_macro_f1(df: pd.DataFrame) -> float:
    return _safe_metric(f1_score, df["y_true"], df["y_pred"], average="macro", labels=list(range(4)), zero_division=0)


def _plot_confusion(cm: np.ndarray, labels: list[str], title: str, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(5, 4))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=labels, yticklabels=labels, ax=ax, cbar=False)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _baseline_loso(features_df: pd.DataFrame) -> dict[str, float]:
    """Run a quick LOSO with each baseline; return binary REM F1 per baseline."""
    out: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {
        "Majority": [],
        "HRThreshold": [],
        "Random": [],
    }
    sessions = features_df["session_id"].drop_duplicates().tolist()
    feat_cols = [c for c in features_df.columns if c not in {"session_id", "epoch_start_at", "stage"}]
    for held_out in sessions:
        test_mask = features_df["session_id"] == held_out
        train = features_df[~test_mask]
        test = features_df[test_mask]
        if test.empty or train.empty:
            continue
        X_tr, y_tr = train[feat_cols], train["stage"]
        X_te, y_te = test[feat_cols], test["stage"]
        y_true_bin = (y_te == "REM").astype(int).to_numpy()

        for name, model in (
            ("Majority", MajorityBaseline()),
            ("HRThreshold", HRThresholdBaseline()),
            ("Random", RandomBaseline(seed=42)),
        ):
            model.fit(X_tr, y_tr)
            pred = model.predict(X_te)
            pred_bin = (pred == "REM").astype(int)
            out[name].append((y_true_bin, pred_bin))

    metrics: dict[str, float] = {}
    for name, pairs in out.items():
        if not pairs:
            metrics[name] = float("nan")
            continue
        yt = np.concatenate([p[0] for p in pairs])
        yp = np.concatenate([p[1] for p in pairs])
        metrics[name] = _safe_metric(f1_score, yt, yp, zero_division=0)
    return metrics


def evaluate_run(run_dir: Path | str) -> dict:
    run_dir = Path(run_dir)
    bin_path = run_dir / "binary_rem_preds.parquet"
    mc_path = run_dir / "multiclass_preds.parquet"
    if not bin_path.exists() or not mc_path.exists():
        raise FileNotFoundError(f"Missing preds parquet in {run_dir}")

    bin_df = pd.read_parquet(bin_path)
    mc_df = pd.read_parquet(mc_path)

    # Binary REM
    yt_b = bin_df["y_true"].to_numpy()
    yp_b = bin_df["y_pred"].to_numpy()
    yproba_b = bin_df["y_proba"].to_numpy()

    bin_metrics = {
        "f1": _safe_metric(f1_score, yt_b, yp_b, zero_division=0),
        "precision": _safe_metric(precision_score, yt_b, yp_b, zero_division=0),
        "recall": _safe_metric(recall_score, yt_b, yp_b, zero_division=0),
        "accuracy": _safe_metric(accuracy_score, yt_b, yp_b),
        "roc_auc": _safe_metric(roc_auc_score, yt_b, yproba_b),
        "pr_auc": _safe_metric(average_precision_score, yt_b, yproba_b),
    }
    cm_bin = confusion_matrix(yt_b, yp_b, labels=[0, 1])

    # Multiclass
    yt_m = mc_df["y_true"].to_numpy()
    yp_m = mc_df["y_pred"].to_numpy()
    per_class_f1 = f1_score(yt_m, yp_m, average=None, labels=[0, 1, 2, 3], zero_division=0)
    mc_metrics = {
        "macro_f1": _safe_metric(f1_score, yt_m, yp_m, average="macro", labels=[0, 1, 2, 3], zero_division=0),
        "weighted_f1": _safe_metric(f1_score, yt_m, yp_m, average="weighted", labels=[0, 1, 2, 3], zero_division=0),
        "accuracy": _safe_metric(accuracy_score, yt_m, yp_m),
        "per_class_f1": {CLASS_NAMES[i]: float(v) for i, v in enumerate(per_class_f1)},
    }
    cm_mc = confusion_matrix(yt_m, yp_m, labels=[0, 1, 2, 3])

    # Per-session
    per_session_rows: list[dict] = []
    sids = bin_df["session_id"].drop_duplicates().tolist()
    for sid in sids:
        b_sub = bin_df[bin_df["session_id"] == sid]
        m_sub = mc_df[mc_df["session_id"] == sid]
        per_session_rows.append({
            "session_id": sid,
            "n_epochs": int(len(b_sub)),
            "binary_rem_f1": _binary_session_f1(b_sub),
            "multiclass_macro_f1": _multiclass_session_macro_f1(m_sub),
        })
    per_session = pd.DataFrame(per_session_rows)
    per_session.to_csv(run_dir / "per_session.csv", index=False)

    worst3 = per_session.sort_values("binary_rem_f1").head(3)

    # Baselines (need features cache)
    baseline_metrics: dict[str, float] = {}
    if FEATURES_CACHE.exists():
        features_df = pd.read_parquet(FEATURES_CACHE)
        run_sids = set(bin_df["session_id"].unique().tolist())
        features_df = features_df[features_df["session_id"].isin(run_sids)].reset_index(drop=True)
        if not features_df.empty:
            baseline_metrics = _baseline_loso(features_df)
        else:
            warnings.warn("Features cache present but no overlapping sessions — skipping baselines")
    else:
        warnings.warn(f"Features cache not found at {FEATURES_CACHE} — skipping baselines")

    # Plots
    _plot_confusion(cm_bin, ["not-REM", "REM"], "Binary REM Confusion", run_dir / "confusion_matrix_binary.png")
    _plot_confusion(cm_mc, CLASS_NAMES, "4-class Confusion", run_dir / "confusion_matrix_multiclass.png")

    # Write metrics.json
    metrics_obj = {
        "binary_rem": bin_metrics,
        "multiclass": mc_metrics,
        "baselines_binary_rem_f1": baseline_metrics,
        "n_sessions": len(sids),
        "n_epochs": int(len(bin_df)),
        "worst_sessions": worst3.to_dict(orient="records"),
    }
    with (run_dir / "metrics.json").open("w") as f:
        json.dump(metrics_obj, f, indent=2, default=str)

    rem_f1 = bin_metrics["f1"]
    if rem_f1 > 0.75:
        verdict = "STRONG (>0.75)"
    elif rem_f1 >= 0.65:
        verdict = "USABLE (0.65-0.75)"
    else:
        verdict = "WEAK (<0.65)"

    worst_strs = [f"{r['session_id'][:8]} (f1={r['binary_rem_f1']:.2f})" for r in worst3.to_dict(orient="records")]

    print(f"\n=== Daybook Classifier Run: {run_dir.name} ===")
    print(f"Sessions: {len(sids)}, Total epochs: {len(bin_df)}")
    print("Binary REM:")
    print(
        f"  F1: {bin_metrics['f1']:.2f}  Precision: {bin_metrics['precision']:.2f}  "
        f"Recall: {bin_metrics['recall']:.2f}  Acc: {bin_metrics['accuracy']:.2f}"
    )
    print(f"  ROC-AUC: {bin_metrics['roc_auc']:.2f}  PR-AUC: {bin_metrics['pr_auc']:.2f}")
    print("Baselines (binary REM F1):")
    if baseline_metrics:
        print(
            f"  Majority: {baseline_metrics.get('Majority', float('nan')):.2f}  "
            f"HRThreshold: {baseline_metrics.get('HRThreshold', float('nan')):.2f}  "
            f"Random: {baseline_metrics.get('Random', float('nan')):.2f}"
        )
    else:
        print("  (skipped — no features cache)")
    print("4-class:")
    print(f"  Macro F1: {mc_metrics['macro_f1']:.2f}  Weighted F1: {mc_metrics['weighted_f1']:.2f}")
    pc = mc_metrics["per_class_f1"]
    print(
        f"  Per-class F1: AWAKE={pc['AWAKE']:.2f}  CORE={pc['CORE']:.2f}  "
        f"DEEP={pc['DEEP']:.2f}  REM={pc['REM']:.2f}"
    )
    print("Verdict:")
    print(f"  REM F1 = {rem_f1:.2f}  ->  {verdict}")
    print(f"  Worst 3 nights: [{', '.join(worst_strs)}]")

    return metrics_obj


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("run_dir", type=str)
    args = p.parse_args()
    evaluate_run(args.run_dir)


if __name__ == "__main__":
    main()
