"""Daybook sleep-stage classifier.

Per-module responsibilities:
    data.py       -- load sessions/sensors/labels from Neon, expand stage segments
    features.py   -- per-epoch feature extraction from aligned sensor + label data
    baselines.py  -- naive baselines XGBoost must beat
    train.py      -- LOSO cross-validation training loop
    evaluate.py   -- metrics, confusion matrix, per-session breakdown

Data layout assumption: a single Apple-HealthKit user; sensor_readings have NULL
session_id (a parser-side import quirk) and are joined to sessions by
user_id + time range. Stage labels are stored as segments (one row per stage
transition) and must be expanded into 30-second epochs before training.
"""
