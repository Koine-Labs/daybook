"""Train the production binary REM model on ALL 249 sessions (no holdout).

LOSO is for honest evaluation. Production deployment needs a single model
trained on everything. Saves model + sidecar metadata.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent.parent))

FEATURES_CACHE = ROOT / "runs" / "_features_cache.parquet"
MODELS_DIR = ROOT / "models"

PURE_BIO_DROP = {"hour_of_day_sin", "hour_of_day_cos", "day_of_week", "is_weekend", "time_of_night_frac"}

XGB_PARAMS = dict(
    n_estimators=400,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.9,
    colsample_bytree=0.9,
    objective="binary:logistic",
    eval_metric="logloss",
    n_jobs=4,
    tree_method="hist",
    random_state=42,
)

CHOSEN_THRESHOLD = 0.23  # from V2 ablation tuning


def main() -> None:
    if not FEATURES_CACHE.exists():
        raise SystemExit(f"Features cache missing: {FEATURES_CACHE}")

    print(f"Loading {FEATURES_CACHE} ...")
    df = pd.read_parquet(FEATURES_CACHE)

    drop_cols = list(PURE_BIO_DROP & set(df.columns))
    feature_cols = [c for c in df.columns if c not in {"session_id", "epoch_start_at", "stage"} | PURE_BIO_DROP]
    print(f"Dropping time features: {drop_cols}")
    print(f"Using {len(feature_cols)} bio features")

    X = df[feature_cols]
    y = (df["stage"] == "REM").astype(int).to_numpy()
    print(f"Training on {len(df):,} epochs ({y.sum():,} REM = {y.mean()*100:.1f}%)")

    t0 = time.monotonic()
    model = xgb.XGBClassifier(**XGB_PARAMS)
    model.fit(X, y, verbose=False)
    dt = time.monotonic() - t0
    print(f"Trained in {dt:.1f}s")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "production_binary_rem.json"
    model.save_model(str(model_path))

    sidecar = {
        "model_kind": "binary_rem_xgboost",
        "model_path": str(model_path.name),
        "trained_at": datetime.now().isoformat(),
        "n_training_epochs": int(len(df)),
        "n_training_sessions": int(df["session_id"].nunique()),
        "n_positive": int(y.sum()),
        "n_negative": int((y == 0).sum()),
        "feature_cols": feature_cols,
        "dropped_time_features": drop_cols,
        "xgb_params": {k: (v if not isinstance(v, np.generic) else v.item()) for k, v in XGB_PARAMS.items()},
        "chosen_threshold": CHOSEN_THRESHOLD,
        "tuned_metrics_from_loso_v2": {
            "f1": 0.449,
            "precision": 0.378,
            "recall": 0.554,
            "roc_auc": 0.716,
        },
        "stage_label_meaning": "1 = REM, 0 = AWAKE/CORE/DEEP",
        "epoch_seconds": 30,
        "context_seconds": 300,
    }
    sidecar_path = MODELS_DIR / "production_binary_rem.meta.json"
    with sidecar_path.open("w") as f:
        json.dump(sidecar, f, indent=2)

    print(f"Saved model:    {model_path}")
    print(f"Saved sidecar:  {sidecar_path}")

    # Verify load roundtrip
    m2 = xgb.XGBClassifier()
    m2.load_model(str(model_path))
    proba = m2.predict_proba(X.iloc[:5])
    print(f"Roundtrip OK. Sample probas (first 5 rows): {proba[:, 1].round(3).tolist()}")


if __name__ == "__main__":
    main()
