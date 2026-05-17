"""
Visualization module for Lullaby sleep analysis.

Produces multi-panel sleep timeline plots, feature distribution comparisons,
and epoch heatmaps with sleep stage color coding.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns

from lullaby.loader import SleepSessionData
from lullaby.features import align_to_epochs, get_feature_columns


# ---------------------------------------------------------------------------
# Color scheme
# ---------------------------------------------------------------------------

STAGE_COLORS = {
    "remSleep":  "#E74C3C",   # Red
    "deepSleep": "#2980B9",   # Blue
    "coreLight": "#76D7C4",   # Teal
    "awake":     "#F39C12",   # Amber
    "inBed":     "#95A5A6",   # Gray
    "unknown":   "#BDC3C7",   # Light gray
}

STAGE_LABELS = {
    "remSleep":  "REM",
    "deepSleep": "Deep",
    "coreLight": "Light",
    "awake":     "Awake",
    "inBed":     "In Bed",
    "unknown":   "Unknown",
}

STAGE_ORDER = ["awake", "remSleep", "coreLight", "deepSleep", "inBed"]


# ---------------------------------------------------------------------------
# Main overview plot
# ---------------------------------------------------------------------------

def plot_night_overview(
    session: SleepSessionData,
    epochs: Optional[pd.DataFrame] = None,
    figsize: tuple[float, float] = (16, 12),
) -> plt.Figure:
    """Plot a multi-panel night overview with all sensor streams.

    Panels (top to bottom, shared x-axis in hours):
    1. Sleep stages — color-coded horizontal bands
    2. Heart rate — line plot
    3. HRV (SDNN) — scatter plot
    4. Motion magnitude — line plot
    5. Breathing rate — line plot from sonar
    6. Audio energy — line plot of RMS energy

    Args:
        session: Loaded sleep session data.
        epochs: Pre-computed epochs (optional, computed if None).
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    fig, axes = plt.subplots(6, 1, figsize=figsize, sharex=True,
                             gridspec_kw={"height_ratios": [1, 2, 2, 2, 2, 2]})

    total_hours = session.duration_hours

    # --- Panel 1: Sleep stages ---
    ax = axes[0]
    _plot_sleep_stage_bands(ax, session.sleep_stages, total_hours)
    ax.set_ylabel("Stage")
    ax.set_title(f"Sleep Session — {session.duration_hours:.1f} hours", fontsize=14, fontweight="bold")

    # REM shading for other panels
    rem_intervals = _get_rem_intervals(session.sleep_stages)

    # --- Panel 2: Heart rate ---
    ax = axes[1]
    if not session.heart_rate.empty:
        hours = session.heart_rate["timestamp"] / 3600
        ax.plot(hours, session.heart_rate["bpm"], linewidth=0.5, color="#2C3E50", alpha=0.8)
        _add_rem_shading(ax, rem_intervals)
    ax.set_ylabel("HR (bpm)")
    ax.grid(True, alpha=0.3)

    # --- Panel 3: HRV ---
    ax = axes[2]
    if not session.hrv.empty:
        hours = session.hrv["timestamp"] / 3600
        ax.scatter(hours, session.hrv["sdnn"], s=20, color="#8E44AD", alpha=0.7, zorder=5)
        _add_rem_shading(ax, rem_intervals)
    ax.set_ylabel("HRV SDNN (ms)")
    ax.grid(True, alpha=0.3)

    # --- Panel 4: Motion magnitude ---
    ax = axes[3]
    if not session.accelerometer.empty:
        # Downsample for plotting (10Hz is too dense)
        accel = session.accelerometer
        mag = np.sqrt(accel["x"]**2 + accel["y"]**2 + accel["z"]**2)
        motion = np.abs(mag - 1.0)

        # Resample to ~1 sample per second for plotting
        step = max(1, len(motion) // int(total_hours * 3600))
        hours = accel["timestamp"].iloc[::step] / 3600
        motion_ds = motion.iloc[::step]
        ax.plot(hours, motion_ds, linewidth=0.3, color="#27AE60", alpha=0.6)
        _add_rem_shading(ax, rem_intervals)
    ax.set_ylabel("Motion (G)")
    ax.grid(True, alpha=0.3)

    # --- Panel 5: Breathing rate ---
    ax = axes[4]
    if not session.sonar.empty:
        hours = session.sonar["timestamp"] / 3600
        br = session.sonar["breathing_rate"]
        valid = br.notna()
        ax.plot(hours[valid], br[valid], linewidth=0.8, color="#E67E22", alpha=0.8)
        _add_rem_shading(ax, rem_intervals)
    ax.set_ylabel("Breathing\n(bpm)")
    ax.grid(True, alpha=0.3)

    # --- Panel 6: Audio energy ---
    ax = axes[5]
    if not session.audio.empty:
        hours = session.audio["timestamp"] / 3600
        ax.plot(hours, session.audio["rms_energy"], linewidth=0.5, color="#3498DB", alpha=0.7)
        _add_rem_shading(ax, rem_intervals)
    ax.set_ylabel("Audio RMS\n(dB)")
    ax.set_xlabel("Time (hours since session start)")
    ax.grid(True, alpha=0.3)

    # Add legend for sleep stages
    legend_patches = [
        mpatches.Patch(color=STAGE_COLORS[s], label=STAGE_LABELS[s])
        for s in STAGE_ORDER if s in STAGE_COLORS
    ]
    fig.legend(handles=legend_patches, loc="upper right", ncol=len(legend_patches),
               fontsize=9, framealpha=0.9)

    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Feature distribution plots
# ---------------------------------------------------------------------------

def plot_feature_distributions(
    epochs: pd.DataFrame,
    features: Optional[list[str]] = None,
    figsize: tuple[float, float] = (16, 10),
) -> plt.Figure:
    """Plot feature distributions grouped by sleep stage.

    Creates violin plots showing how each feature distributes across
    different sleep stages. Useful for identifying which features
    best separate REM from non-REM.

    Args:
        epochs: Epoch-aligned feature DataFrame.
        features: List of feature columns to plot. If None, uses all numeric features.
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    if features is None:
        features = get_feature_columns(epochs)

    # Filter epochs with valid sleep stages
    valid = epochs[epochs["sleep_stage"].isin(STAGE_ORDER)].copy()
    if valid.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No sleep stage data available", ha="center", va="center")
        return fig

    n_features = len(features)
    ncols = 3
    nrows = int(np.ceil(n_features / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, squeeze=False)
    axes = axes.flatten()

    # Custom palette for stages
    palette = {s: STAGE_COLORS[s] for s in STAGE_ORDER}

    for idx, feat in enumerate(features):
        ax = axes[idx]
        data = valid[["sleep_stage", feat]].dropna()
        if data.empty:
            ax.set_visible(False)
            continue

        sns.violinplot(
            data=data,
            x="sleep_stage",
            y=feat,
            hue="sleep_stage",
            order=[s for s in STAGE_ORDER if s in data["sleep_stage"].values],
            hue_order=[s for s in STAGE_ORDER if s in data["sleep_stage"].values],
            palette=palette,
            ax=ax,
            inner="box",
            linewidth=0.8,
            cut=0,
            legend=False,
        )
        ax.set_title(feat, fontsize=10)
        ax.set_xlabel("")
        ax.tick_params(axis="x", rotation=45)

    # Hide unused axes
    for idx in range(n_features, len(axes)):
        axes[idx].set_visible(False)

    fig.suptitle("Feature Distributions by Sleep Stage", fontsize=14, fontweight="bold")
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Epoch heatmap
# ---------------------------------------------------------------------------

def plot_epoch_heatmap(
    epochs: pd.DataFrame,
    features: Optional[list[str]] = None,
    figsize: tuple[float, float] = (14, 10),
) -> plt.Figure:
    """Plot a heatmap of normalized features over time with stage color bar.

    Rows = epochs (time), columns = z-scored features. A color sidebar
    shows the sleep stage for each epoch.

    Args:
        epochs: Epoch-aligned feature DataFrame.
        features: List of feature columns. If None, uses all numeric features.
        figsize: Figure dimensions.

    Returns:
        matplotlib Figure.
    """
    if features is None:
        features = get_feature_columns(epochs)

    # Z-score normalization
    feat_data = epochs[features].copy()
    feat_data = (feat_data - feat_data.mean()) / feat_data.std()
    feat_data = feat_data.fillna(0)

    # Create figure with two axes: stage bar + heatmap
    fig, (ax_stage, ax_heat) = plt.subplots(
        1, 2, figsize=figsize,
        gridspec_kw={"width_ratios": [1, 20]},
        sharey=True,
    )

    # Stage color bar
    stage_colors_mapped = [
        STAGE_COLORS.get(s, "#FFFFFF") if s else "#FFFFFF"
        for s in epochs["sleep_stage"]
    ]
    for i, color in enumerate(stage_colors_mapped):
        ax_stage.barh(i, 1, color=color, edgecolor="none")
    ax_stage.set_xlim(0, 1)
    ax_stage.set_xlabel("Stage")
    ax_stage.set_xticks([])
    ax_stage.invert_yaxis()

    # Heatmap
    sns.heatmap(
        feat_data,
        ax=ax_heat,
        cmap="RdBu_r",
        center=0,
        vmin=-3,
        vmax=3,
        xticklabels=features,
        yticklabels=False,
        cbar_kws={"label": "Z-score", "shrink": 0.8},
    )
    ax_heat.set_xlabel("Features")

    # Y-axis labels as hours
    n_epochs = len(epochs)
    tick_positions = np.linspace(0, n_epochs - 1, min(8, n_epochs)).astype(int)
    ax_heat.set_yticks(tick_positions)
    ax_heat.set_yticklabels(
        [f"{epochs.iloc[i]['epoch_time_hours']:.1f}h" for i in tick_positions]
    )

    fig.suptitle("Feature Heatmap Over Time", fontsize=14, fontweight="bold")
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _plot_sleep_stage_bands(
    ax: plt.Axes,
    stages_df: pd.DataFrame,
    total_hours: float,
) -> None:
    """Draw colored horizontal bands for each sleep stage interval."""
    if stages_df.empty:
        ax.text(total_hours / 2, 0.5, "No sleep stage data",
                ha="center", va="center", fontsize=10, color="gray")
        ax.set_xlim(0, total_hours)
        ax.set_ylim(0, 1)
        ax.set_yticks([])
        return

    for _, row in stages_df.iterrows():
        start_h = row["start"] / 3600
        end_h = row["end"] / 3600
        stage = row["stage"]
        color = STAGE_COLORS.get(stage, "#BDC3C7")
        ax.barh(0.5, end_h - start_h, left=start_h, height=0.8,
                color=color, edgecolor="white", linewidth=0.5)

    ax.set_xlim(0, total_hours)
    ax.set_ylim(0, 1)
    ax.set_yticks([])


def _get_rem_intervals(stages_df: pd.DataFrame) -> list[tuple[float, float]]:
    """Extract REM sleep intervals as list of (start_hours, end_hours)."""
    if stages_df.empty:
        return []
    rem = stages_df[stages_df["stage"] == "remSleep"]
    return [(row["start"] / 3600, row["end"] / 3600) for _, row in rem.iterrows()]


def _add_rem_shading(
    ax: plt.Axes,
    rem_intervals: list[tuple[float, float]],
) -> None:
    """Add light red shading for REM intervals to a plot axis."""
    for start_h, end_h in rem_intervals:
        ax.axvspan(start_h, end_h, alpha=0.15, color=STAGE_COLORS["remSleep"],
                   zorder=0)
