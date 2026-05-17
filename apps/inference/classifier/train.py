from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

try:
    from .data import DEFAULT_USER_ID, list_sessions, load_sessions
    from .features import compute_all_features
except ImportError:
    from data import DEFAULT_USER_ID, list_sessions, load_sessions  # type: ignore[no-redef]
    from features import compute_all_features  # type: ignore[no-redef]

RUNS_DIR = Path(__file__).parent / "runs"
FEATURES_CACHE = RUNS_DIR / "_features_cache.parquet"

NON_FEATURE_COLS = {"session_id", "epoch_start_at", "stage"}

STAGE_TO_INT = {"AWAKE": 0, "CORE": 1, "DEEP": 2, "REM": 3}
INT_TO_STAGE = {v: k for k, v in STAGE_TO_INT.items()}

XGB_PARAMS_BINARY = dict(
    n_estimators=400,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.9,
    colsample_bytree=0.9,
    objective="binary:logistic",
    eval_metric="logloss",
    n_jobs=4,
    tree_method="hist",
)
XGB_PARAMS_MULTI = dict(
    n_estimators=400,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.9,
    colsample_bytree=0.9,
    objective="multi:softprob",
    eval_metric="mlogloss",
    n_jobs=4,
    tree_method="hist",
)


def _feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in NON_FEATURE_COLS]


def _val_split_sessions(train_sessions: list[str], frac: float = 0.15, seed: int = 42) -> tuple[list[str], list[str]]:
    rng = np.random.default_rng(seed)
    n_val = int(np.floor(frac * len(train_sessions)))
    n_val = max(1, n_val) if len(train_sessions) >= 2 else 0
    perm = rng.permutation(len(train_sessions))
    val_idx = set(perm[:n_val].tolist())
    val = [train_sessions[i] for i in sorted(val_idx)]
    tr = [s for i, s in enumerate(train_sessions) if i not in val_idx]
    return tr, val


def run_loso(
    features_df: pd.DataFrame,
    run_dir: Path | None = None,
    early_stopping_rounds: int = 25,
) -> Path:
    """Leave-one-session-out LOSO with XGBoost (binary REM + 4-class)."""
    if run_dir is None:
        run_dir = RUNS_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "models").mkdir(exist_ok=True)

    feature_cols = _feature_columns(features_df)
    session_ids = (
        features_df.sort_values("epoch_start_at")["session_id"].drop_duplicates().tolist()
    )
    n_sessions = len(session_ids)
    print(f"LOSO over {n_sessions} sessions, {len(features_df)} epochs, {len(feature_cols)} features")

    binary_rows: list[dict] = []
    multi_rows: list[dict] = []

    t_start = time.monotonic()

    for fold_i, held_out in enumerate(session_ids, 1):
        t_fold = time.monotonic()
        test_mask = features_df["session_id"] == held_out
        test_df = features_df[test_mask]
        train_df_all = features_df[~test_mask]
        train_sessions = [s for s in session_ids if s != held_out]

        tr_sessions, val_sessions = _val_split_sessions(train_sessions)
        if len(val_sessions) == 0:
            tr_df = train_df_all
            val_df = test_df.iloc[0:0]
        else:
            tr_df = train_df_all[train_df_all["session_id"].isin(tr_sessions)]
            val_df = train_df_all[train_df_all["session_id"].isin(val_sessions)]

        X_tr = tr_df[feature_cols]
        X_val = val_df[feature_cols]
        X_te = test_df[feature_cols]

        # binary REM
        y_tr_bin = (tr_df["stage"] == "REM").astype(int).to_numpy()
        y_val_bin = (val_df["stage"] == "REM").astype(int).to_numpy()
        y_te_bin = (test_df["stage"] == "REM").astype(int).to_numpy()

        bin_params = dict(XGB_PARAMS_BINARY)
        bin_kwargs = {"random_state": 42}
        if len(X_val) > 0 and len(np.unique(y_val_bin)) > 1:
            bin_kwargs["early_stopping_rounds"] = early_stopping_rounds
        bin_model = xgb.XGBClassifier(**bin_params, **bin_kwargs)
        fit_kwargs_bin: dict = {"verbose": False}
        if "early_stopping_rounds" in bin_kwargs:
            fit_kwargs_bin["eval_set"] = [(X_val, y_val_bin)]
        bin_model.fit(X_tr, y_tr_bin, **fit_kwargs_bin)
        proba_bin = bin_model.predict_proba(X_te)[:, 1]
        pred_bin = (proba_bin >= 0.5).astype(int)
        bin_model.save_model(str(run_dir / "models" / f"{held_out}_binary.json"))

        for ts, yt, yp, yp_proba in zip(
            test_df["epoch_start_at"].to_list(),
            y_te_bin.tolist(),
            pred_bin.tolist(),
            proba_bin.tolist(),
        ):
            binary_rows.append({
                "session_id": held_out,
                "epoch_start_at": ts,
                "y_true": int(yt),
                "y_pred": int(yp),
                "y_proba": float(yp_proba),
            })

        # 4-class
        y_tr_mc = tr_df["stage"].map(STAGE_TO_INT).to_numpy()
        y_val_mc = val_df["stage"].map(STAGE_TO_INT).to_numpy()
        y_te_mc = test_df["stage"].map(STAGE_TO_INT).to_numpy()

        mc_params = dict(XGB_PARAMS_MULTI)
        mc_kwargs = {"random_state": 42, "num_class": 4}
        if len(X_val) > 0 and len(np.unique(y_val_mc)) > 1:
            mc_kwargs["early_stopping_rounds"] = early_stopping_rounds
        mc_model = xgb.XGBClassifier(**mc_params, **mc_kwargs)
        fit_kwargs_mc: dict = {"verbose": False}
        if "early_stopping_rounds" in mc_kwargs:
            fit_kwargs_mc["eval_set"] = [(X_val, y_val_mc)]
        mc_model.fit(X_tr, y_tr_mc, **fit_kwargs_mc)
        proba_mc = mc_model.predict_proba(X_te)
        pred_mc = proba_mc.argmax(axis=1)
        mc_model.save_model(str(run_dir / "models" / f"{held_out}_multi.json"))

        # ensure 4 probability columns even if a class was missing in train
        full_proba = np.zeros((len(X_te), 4), dtype="float64")
        for j, cls in enumerate(getattr(mc_model, "classes_", np.arange(4))):
            cls_i = int(cls)
            if 0 <= cls_i < 4:
                full_proba[:, cls_i] = proba_mc[:, j]

        for k, ts in enumerate(test_df["epoch_start_at"].to_list()):
            multi_rows.append({
                "session_id": held_out,
                "epoch_start_at": ts,
                "y_true": int(y_te_mc[k]),
                "y_pred": int(pred_mc[k]),
                "proba_AWAKE": float(full_proba[k, 0]),
                "proba_CORE": float(full_proba[k, 1]),
                "proba_DEEP": float(full_proba[k, 2]),
                "proba_REM": float(full_proba[k, 3]),
            })

        dt = time.monotonic() - t_fold
        n_te = int(test_mask.sum())
        rem_te = int((test_df["stage"] == "REM").sum())
        print(
            f"[{fold_i}/{n_sessions}] held_out={held_out[:8]} "
            f"epochs={n_te} REM={rem_te} "
            f"bin_best_iter={getattr(bin_model, 'best_iteration', 'N/A')} "
            f"mc_best_iter={getattr(mc_model, 'best_iteration', 'N/A')} "
            f"in {dt:.1f}s"
        )

    bin_df = pd.DataFrame(binary_rows)
    mc_df = pd.DataFrame(multi_rows)
    bin_df.to_parquet(run_dir / "binary_rem_preds.parquet", index=False)
    mc_df.to_parquet(run_dir / "multiclass_preds.parquet", index=False)

    runtime = time.monotonic() - t_start
    stages_in_data = sorted(features_df["stage"].unique().tolist())
    meta = {
        "timestamp": datetime.now().isoformat(),
        "n_sessions": int(n_sessions),
        "n_epochs": int(len(features_df)),
        "feature_cols": feature_cols,
        "xgb_params_binary": XGB_PARAMS_BINARY,
        "xgb_params_multi": XGB_PARAMS_MULTI,
        "stages_in_data": stages_in_data,
        "stage_to_int": STAGE_TO_INT,
        "runtime_seconds": float(runtime),
        "early_stopping_rounds": int(early_stopping_rounds),
    }
    with (run_dir / "meta.json").open("w") as f:
        json.dump(meta, f, indent=2, default=str)

    print(f"\nLOSO complete in {runtime:.1f}s — wrote {run_dir}")
    return run_dir


def _load_or_compute_features(max_sessions: int | None, use_cache: bool) -> pd.DataFrame:
    if use_cache and FEATURES_CACHE.exists():
        print(f"Loading cached features from {FEATURES_CACHE}")
        df = pd.read_parquet(FEATURES_CACHE)
        if max_sessions is not None:
            keep = (
                df.sort_values("epoch_start_at")["session_id"]
                .drop_duplicates()
                .head(max_sessions)
                .tolist()
            )
            df = df[df["session_id"].isin(keep)].reset_index(drop=True)
        return df

    print("Listing eligible sessions from DB...")
    sessions = list_sessions(user_id=DEFAULT_USER_ID)
    sessions = sessions.sort_values("started_at").reset_index(drop=True)
    if max_sessions is not None:
        sessions = sessions.head(max_sessions)
    ids = sessions["id"].tolist()
    print(f"Loading {len(ids)} session bundles...")
    bundles = load_sessions(ids, use_cache=True)
    print(f"Computing features for {len(bundles)} sessions...")
    features = compute_all_features(bundles)

    if use_cache:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        features.to_parquet(FEATURES_CACHE, index=False)
        print(f"Cached features to {FEATURES_CACHE}")
    return features


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--max-sessions", type=int, default=None, help="Limit to first N sessions chronologically")
    p.add_argument("--cache-features", action="store_true", help="Use cached features parquet if present")
    p.add_argument("--early-stopping-rounds", type=int, default=25)
    args = p.parse_args()

    features = _load_or_compute_features(args.max_sessions, args.cache_features)
    if features.empty:
        raise RuntimeError("No features produced — aborting")

    print(f"\nFeatures shape: {features.shape}")
    print(f"Stage counts: {features['stage'].value_counts().to_dict()}")

    run_dir = run_loso(features, early_stopping_rounds=args.early_stopping_rounds)
    print(f"\nRun dir: {run_dir}")


if __name__ == "__main__":
    main()
