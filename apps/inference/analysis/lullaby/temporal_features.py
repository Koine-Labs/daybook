"""
Temporal feature engineering for Lullaby sleep classification.

Extends the base epoch features from ``features.py`` with multi-epoch
context: rolling statistics, epoch-over-epoch deltas, time-of-night
encoding, and audio one-hot classification features.  These ~32 new
features capture temporal dynamics that are critical for distinguishing
REM from non-REM sleep.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from lullaby.features import get_feature_columns


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Base features used for rolling / delta calculations
_BASE_FEATURES = [
    "hr_mean",
    "hrv_mean",
    "accel_mag_mean",
    "breathing_rate_mean",
    "breathing_regularity_mean",
]

# All known audio classification labels from the iOS app
_AUDIO_CLASSES = ["breathing", "silence", "snoring", "movement"]
# "ambientNoise" is the implicit reference category (not one-hot encoded)


@dataclass(frozen=True)
class TemporalFeatureConfig:
    """Controls which temporal features are generated and how."""

    rolling_windows: tuple[int, ...] = (3, 5)
    enable_rolling_mean: bool = True
    enable_rolling_std: bool = True
    enable_deltas: bool = True
    enable_time_of_night: bool = True
    enable_audio_onehot: bool = True
    enable_iev: bool = True
    fill_strategy: str = "ffill_then_zero"  # "ffill_then_zero" | "zero" | "none"
    base_features: tuple[str, ...] = tuple(_BASE_FEATURES)


DEFAULT_CONFIG = TemporalFeatureConfig()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_temporal_features(
    epochs: pd.DataFrame,
    config: Optional[TemporalFeatureConfig] = None,
) -> pd.DataFrame:
    """Add temporal context features to an epoch DataFrame.

    Takes the output of ``align_to_epochs()`` and adds rolling statistics,
    deltas, time-of-night, audio one-hot encoding, and inter-epoch heart
    rate variability features.

    Args:
        epochs: DataFrame from ``align_to_epochs()``.  Must contain at
            least ``epoch_start`` and ``epoch_end`` columns.
        config: Feature generation settings.  ``None`` uses defaults.

    Returns:
        A *copy* of *epochs* with new columns appended.  The original
        DataFrame is not modified.
    """
    if config is None:
        config = DEFAULT_CONFIG

    df = epochs.copy()

    if df.empty:
        return df

    # Determine which base features actually exist in this DataFrame
    available = [f for f in config.base_features if f in df.columns]

    # --- Rolling statistics ---
    if config.enable_rolling_mean:
        for win in config.rolling_windows:
            for feat in available:
                col = f"{feat}_roll{win}_mean"
                df[col] = df[feat].rolling(window=win, min_periods=1).mean()

    if config.enable_rolling_std:
        for win in config.rolling_windows:
            for feat in available:
                col = f"{feat}_roll{win}_std"
                df[col] = df[feat].rolling(window=win, min_periods=1).std()
                # Single-value windows produce NaN for std → fill with 0
                df[col] = df[col].fillna(0.0)

    # --- Epoch-over-epoch deltas ---
    if config.enable_deltas:
        for feat in available:
            col = f"{feat}_delta"
            df[col] = df[feat].diff()

    # --- Time of night ---
    if config.enable_time_of_night and "epoch_start" in df.columns and "epoch_end" in df.columns:
        session_start = df["epoch_start"].iloc[0]
        session_end = df["epoch_end"].iloc[-1]
        session_duration = session_end - session_start
        if session_duration > 0:
            midpoints = (df["epoch_start"] + df["epoch_end"]) / 2
            df["time_of_night"] = (midpoints - session_start) / session_duration
        else:
            df["time_of_night"] = 0.0

    # --- Audio one-hot encoding ---
    if config.enable_audio_onehot and "dominant_classification" in df.columns:
        for cls in _AUDIO_CLASSES:
            col = f"audio_is_{cls}"
            df[col] = (df["dominant_classification"] == cls).astype(float)

    # --- Inter-epoch heart rate variability ---
    if config.enable_iev and "hr_mean" in df.columns:
        for win in config.rolling_windows:
            col = f"hr_mean_iev_{win}"
            df[col] = df["hr_mean"].rolling(window=win, min_periods=1).std()
            df[col] = df[col].fillna(0.0)

    # --- Fill strategy ---
    df = _apply_fill_strategy(df, config.fill_strategy)

    return df


def get_temporal_feature_names(config: Optional[TemporalFeatureConfig] = None) -> list[str]:
    """Return the names of all temporal features that would be generated.

    Useful for verifying feature counts in tests and documentation.
    """
    if config is None:
        config = DEFAULT_CONFIG

    names: list[str] = []
    available = list(config.base_features)

    if config.enable_rolling_mean:
        for win in config.rolling_windows:
            for feat in available:
                names.append(f"{feat}_roll{win}_mean")

    if config.enable_rolling_std:
        for win in config.rolling_windows:
            for feat in available:
                names.append(f"{feat}_roll{win}_std")

    if config.enable_deltas:
        for feat in available:
            names.append(f"{feat}_delta")

    if config.enable_time_of_night:
        names.append("time_of_night")

    if config.enable_audio_onehot:
        for cls in _AUDIO_CLASSES:
            names.append(f"audio_is_{cls}")

    if config.enable_iev:
        for win in config.rolling_windows:
            names.append(f"hr_mean_iev_{win}")

    return names


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_fill_strategy(df: pd.DataFrame, strategy: str) -> pd.DataFrame:
    """Fill NaN values in numeric columns according to the chosen strategy."""
    if strategy == "none":
        return df

    numeric_cols = df.select_dtypes(include=[np.number]).columns

    if strategy == "ffill_then_zero":
        df[numeric_cols] = df[numeric_cols].ffill()
        df[numeric_cols] = df[numeric_cols].fillna(0.0)
    elif strategy == "zero":
        df[numeric_cols] = df[numeric_cols].fillna(0.0)

    return df
