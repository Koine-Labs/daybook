"""Retrain LOSO on feature subsets to isolate physiology-vs-time contribution.

Variants:
  v1_no_calendar:  drop hour_of_day_sin/cos, day_of_week, is_weekend  (keep time_of_night_frac)
  v2_pure_bio:     drop ALL time features including time_of_night_frac

Each variant runs full LOSO and saves to its own run directory.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from classifier.train import run_loso, FEATURES_CACHE  # noqa: E402

CALENDAR_FEATURES = {"hour_of_day_sin", "hour_of_day_cos", "day_of_week", "is_weekend"}
SESSION_TIME_FEATURE = {"time_of_night_frac"}


def main() -> None:
    if not FEATURES_CACHE.exists():
        raise SystemExit(f"Features cache not found at {FEATURES_CACHE}. Run train.py --cache-features first.")

    print(f"Loading features cache from {FEATURES_CACHE} ...")
    features = pd.read_parquet(FEATURES_CACHE)
    print(f"Loaded {len(features):,} epochs, columns={len(features.columns)}")

    base_dir = ROOT / "runs"

    # Variant 1: drop calendar features, keep session-relative time
    drop_v1 = CALENDAR_FEATURES & set(features.columns)
    print(f"\n=== Variant 1: drop calendar features {sorted(drop_v1)} ===")
    feats_v1 = features.drop(columns=list(drop_v1))
    print(f"Feature DataFrame shape: {feats_v1.shape}")
    run1 = run_loso(feats_v1, run_dir=base_dir / "20260517_v1_no_calendar")
    print(f"V1 written to {run1}")

    # Variant 2: drop ALL time features
    drop_v2 = (CALENDAR_FEATURES | SESSION_TIME_FEATURE) & set(features.columns)
    print(f"\n=== Variant 2: drop ALL time features {sorted(drop_v2)} ===")
    feats_v2 = features.drop(columns=list(drop_v2))
    print(f"Feature DataFrame shape: {feats_v2.shape}")
    run2 = run_loso(feats_v2, run_dir=base_dir / "20260517_v2_pure_bio")
    print(f"V2 written to {run2}")

    print("\nDone. Evaluate with:")
    print(f"  python -m classifier.evaluate {run1}/")
    print(f"  python -m classifier.evaluate {run2}/")


if __name__ == "__main__":
    main()
