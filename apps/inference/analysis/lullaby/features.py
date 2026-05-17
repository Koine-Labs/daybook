"""
Epoch alignment and feature engineering for Lullaby sleep analysis.

Aligns all sensor streams to uniform 30-second epochs (matching Apple's
sleep stage resolution) and computes derived features for statistical analysis.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from lullaby.loader import SleepSessionData


def align_to_epochs(
    session: SleepSessionData,
    epoch_seconds: float = 30.0,
) -> pd.DataFrame:
    """Align all sensor streams to uniform time epochs.

    For each epoch window, aggregates sensor data into summary features.
    This is the core function that transforms raw sensor timeseries into
    a feature matrix suitable for statistical comparison and ML.

    Args:
        session: Loaded sleep session data.
        epoch_seconds: Width of each epoch in seconds (default 30s to
            match Apple's sleep stage resolution).

    Returns:
        DataFrame where each row is one epoch. Columns include:
        - epoch_start, epoch_end: Time boundaries (seconds since session start)
        - epoch_time_hours: Epoch midpoint in hours (for plotting)
        - HR features: hr_mean, hr_std, hr_min, hr_max, hr_range, hr_count
        - HRV features: hrv_mean (forward-filled)
        - Motion features: accel_mag_mean, accel_mag_std, accel_mag_max, motion_count
        - Sonar features: breathing_rate_mean, breathing_regularity_mean, signal_strength_mean
        - Audio features: rms_energy_mean, spectral_centroid_mean, dominant_classification
        - sleep_stage: Majority-vote stage label for the epoch
    """
    total_seconds = session.duration_hours * 3600
    n_epochs = int(np.ceil(total_seconds / epoch_seconds))

    rows = []
    for i in range(n_epochs):
        epoch_start = i * epoch_seconds
        epoch_end = epoch_start + epoch_seconds
        epoch_mid = epoch_start + epoch_seconds / 2

        row = {
            "epoch_start": epoch_start,
            "epoch_end": epoch_end,
            "epoch_time_hours": epoch_mid / 3600,
        }

        # --- Heart Rate ---
        hr_epoch = _slice_by_timestamp(session.heart_rate, epoch_start, epoch_end)
        if not hr_epoch.empty:
            bpm = hr_epoch["bpm"]
            row["hr_mean"] = bpm.mean()
            row["hr_std"] = bpm.std() if len(bpm) > 1 else 0.0
            row["hr_min"] = bpm.min()
            row["hr_max"] = bpm.max()
            row["hr_range"] = bpm.max() - bpm.min()
            row["hr_count"] = len(bpm)
        else:
            row.update({"hr_mean": np.nan, "hr_std": np.nan, "hr_min": np.nan,
                        "hr_max": np.nan, "hr_range": np.nan, "hr_count": 0})

        # --- HRV ---
        hrv_epoch = _slice_by_timestamp(session.hrv, epoch_start, epoch_end)
        if not hrv_epoch.empty:
            row["hrv_mean"] = hrv_epoch["sdnn"].mean()
        else:
            row["hrv_mean"] = np.nan

        # --- Accelerometer (motion) ---
        accel_epoch = _slice_by_timestamp(session.accelerometer, epoch_start, epoch_end)
        if not accel_epoch.empty:
            # Subtract gravity (approximate: magnitude deviation from 1G)
            mag = np.sqrt(accel_epoch["x"]**2 + accel_epoch["y"]**2 + accel_epoch["z"]**2)
            motion = np.abs(mag - 1.0)  # Deviation from resting 1G
            row["accel_mag_mean"] = motion.mean()
            row["accel_mag_std"] = motion.std() if len(motion) > 1 else 0.0
            row["accel_mag_max"] = motion.max()
            row["motion_count"] = len(motion)
        else:
            row.update({"accel_mag_mean": np.nan, "accel_mag_std": np.nan,
                        "accel_mag_max": np.nan, "motion_count": 0})

        # --- Sonar (breathing) ---
        sonar_epoch = _slice_by_timestamp(session.sonar, epoch_start, epoch_end)
        if not sonar_epoch.empty:
            row["breathing_rate_mean"] = sonar_epoch["breathing_rate"].mean()
            row["breathing_regularity_mean"] = sonar_epoch["breathing_regularity"].mean()
            row["signal_strength_mean"] = sonar_epoch["signal_strength"].mean()
        else:
            row.update({"breathing_rate_mean": np.nan,
                        "breathing_regularity_mean": np.nan,
                        "signal_strength_mean": np.nan})

        # --- Audio ---
        audio_epoch = _slice_by_timestamp(session.audio, epoch_start, epoch_end)
        if not audio_epoch.empty:
            row["rms_energy_mean"] = audio_epoch["rms_energy"].mean()
            row["spectral_centroid_mean"] = audio_epoch["spectral_centroid"].mean()
            # Dominant classification by mode
            row["dominant_classification"] = audio_epoch["classification"].mode().iloc[0]
        else:
            row.update({"rms_energy_mean": np.nan,
                        "spectral_centroid_mean": np.nan,
                        "dominant_classification": None})

        # --- Sleep Stage (majority vote) ---
        row["sleep_stage"] = _majority_stage(session.sleep_stages, epoch_start, epoch_end)

        rows.append(row)

    epochs = pd.DataFrame(rows)

    # Forward-fill HRV (it's very sparse, ~5 min intervals)
    if not epochs.empty and "hrv_mean" in epochs.columns:
        epochs["hrv_mean"] = epochs["hrv_mean"].ffill()

    return epochs


def get_feature_columns(epochs: pd.DataFrame) -> list[str]:
    """Return the list of numeric feature column names (excluding metadata/labels)."""
    exclude = {"epoch_start", "epoch_end", "epoch_time_hours",
               "sleep_stage", "dominant_classification",
               "hr_count", "motion_count"}
    return [c for c in epochs.columns if c not in exclude and epochs[c].dtype in ("float64", "float32", "int64")]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slice_by_timestamp(
    df: pd.DataFrame,
    start: float,
    end: float,
) -> pd.DataFrame:
    """Select rows where timestamp falls within [start, end)."""
    if df.empty:
        return df
    mask = (df["timestamp"] >= start) & (df["timestamp"] < end)
    return df.loc[mask]


def _majority_stage(
    stages_df: pd.DataFrame,
    epoch_start: float,
    epoch_end: float,
) -> str | None:
    """Determine the dominant sleep stage within an epoch by overlap duration.

    For each sleep stage interval that overlaps the epoch, computes the
    overlap duration. Returns the stage with the most total overlap time.
    """
    if stages_df.empty:
        return None

    # Find all stage intervals that overlap [epoch_start, epoch_end)
    overlapping = stages_df[
        (stages_df["end"] > epoch_start) & (stages_df["start"] < epoch_end)
    ]

    if overlapping.empty:
        return None

    # Compute overlap duration for each
    stage_durations: dict[str, float] = {}
    for _, row in overlapping.iterrows():
        overlap_start = max(row["start"], epoch_start)
        overlap_end = min(row["end"], epoch_end)
        duration = overlap_end - overlap_start
        stage = row["stage"]
        stage_durations[stage] = stage_durations.get(stage, 0) + duration

    # Return stage with most overlap
    return max(stage_durations, key=stage_durations.get)
