"""
Multi-session data pipeline for Lullaby sleep classification.

Handles quality gating, label encoding, temporal feature augmentation,
and session-level train/test splitting for ML training.  Designed to
prevent temporal leakage by splitting at the session (night) level
rather than the epoch level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from lullaby.loader import SleepSessionData, generate_mock_session
from lullaby.features import align_to_epochs, get_feature_columns
from lullaby.quality import assess_quality
from lullaby.temporal_features import (
    add_temporal_features,
    TemporalFeatureConfig,
    DEFAULT_CONFIG as DEFAULT_TEMPORAL_CONFIG,
)


# ---------------------------------------------------------------------------
# Label encoding
# ---------------------------------------------------------------------------

STAGE_LABELS: list[str] = ["awake", "remSleep", "coreLight", "deepSleep", "inBed"]

STAGE_TO_INT: dict[str, int] = {stage: i for i, stage in enumerate(STAGE_LABELS)}

INT_TO_STAGE: dict[int, str] = {i: stage for stage, i in STAGE_TO_INT.items()}


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class ClassificationDataset:
    """Epoch feature matrix with encoded labels, ready for ML."""

    X: np.ndarray                    # (n_epochs, n_features)
    y: np.ndarray                    # (n_epochs,)  integer-encoded labels
    feature_names: list[str]
    session_ids: np.ndarray          # (n_epochs,)  session ID per epoch
    stage_labels: list[str]          # ordered label names (index → name)
    epochs_df: pd.DataFrame          # full DataFrame before X/y extraction


@dataclass
class TrainTestSplit:
    """Session-level train/test split."""

    train: ClassificationDataset
    test: ClassificationDataset
    train_session_ids: list[str]
    test_session_ids: list[str]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def prepare_sessions(
    sessions: list[SleepSessionData],
    min_coverage_pct: float = 80.0,
    temporal_config: Optional[TemporalFeatureConfig] = None,
) -> ClassificationDataset:
    """Process multiple sessions into a single classification dataset.

    Pipeline:
    1. Quality gate — skip sessions below *min_coverage_pct* HR coverage.
    2. Align to 30-second epochs.
    3. Add temporal features.
    4. Drop unlabeled epochs (no sleep stage).
    5. Encode labels as integers.
    6. Concatenate all sessions.

    Args:
        sessions: List of loaded sleep sessions.
        min_coverage_pct: Minimum HR coverage to include a session.
        temporal_config: Temporal feature config (None → defaults).

    Returns:
        A ``ClassificationDataset`` ready for model training.

    Raises:
        ValueError: If no sessions pass the quality gate.
    """
    if temporal_config is None:
        temporal_config = DEFAULT_TEMPORAL_CONFIG

    all_dfs: list[pd.DataFrame] = []

    for session in sessions:
        # Quality gate
        quality = assess_quality(session)
        hr_coverage = quality["heart_rate"]["coverage_pct"]
        if hr_coverage is not None and hr_coverage < min_coverage_pct:
            continue

        # Epoch alignment + temporal features
        epochs = align_to_epochs(session)
        if epochs.empty:
            continue

        epochs = add_temporal_features(epochs, config=temporal_config)

        # Tag with session ID
        epochs["session_id"] = session.session_id

        all_dfs.append(epochs)

    if not all_dfs:
        raise ValueError("No sessions passed quality gate")

    combined = pd.concat(all_dfs, ignore_index=True)

    # Drop epochs without a sleep stage label
    combined = combined.dropna(subset=["sleep_stage"])
    combined = combined[combined["sleep_stage"].isin(STAGE_LABELS)]
    combined = combined.reset_index(drop=True)

    if combined.empty:
        raise ValueError("No labeled epochs remain after filtering")

    return _build_dataset(combined)


def split_by_session(
    dataset: ClassificationDataset,
    test_fraction: float = 0.2,
    seed: int = 42,
) -> TrainTestSplit:
    """Split dataset by session (prevents temporal leakage).

    Randomly assigns whole sessions to train or test sets, ensuring
    that no session's epochs appear in both sets.

    Args:
        dataset: Full classification dataset.
        test_fraction: Approximate fraction of sessions for the test set.
        seed: Random seed for reproducibility.

    Returns:
        A ``TrainTestSplit`` with session-level partitioning.
    """
    rng = np.random.default_rng(seed)
    unique_sessions = list(np.unique(dataset.session_ids))
    rng.shuffle(unique_sessions)

    n_test = max(1, int(len(unique_sessions) * test_fraction))
    test_sessions = set(unique_sessions[:n_test])
    train_sessions = set(unique_sessions[n_test:])

    train_mask = np.isin(dataset.session_ids, list(train_sessions))
    test_mask = np.isin(dataset.session_ids, list(test_sessions))

    train_ds = ClassificationDataset(
        X=dataset.X[train_mask],
        y=dataset.y[train_mask],
        feature_names=dataset.feature_names,
        session_ids=dataset.session_ids[train_mask],
        stage_labels=dataset.stage_labels,
        epochs_df=dataset.epochs_df.loc[train_mask].reset_index(drop=True),
    )
    test_ds = ClassificationDataset(
        X=dataset.X[test_mask],
        y=dataset.y[test_mask],
        feature_names=dataset.feature_names,
        session_ids=dataset.session_ids[test_mask],
        stage_labels=dataset.stage_labels,
        epochs_df=dataset.epochs_df.loc[test_mask].reset_index(drop=True),
    )

    return TrainTestSplit(
        train=train_ds,
        test=test_ds,
        train_session_ids=sorted(train_sessions),
        test_session_ids=sorted(test_sessions),
    )


def get_leave_one_out_splits(
    dataset: ClassificationDataset,
) -> list[TrainTestSplit]:
    """Generate leave-one-session-out cross-validation splits.

    Each split holds out one session for testing and trains on the rest.

    Returns:
        List of ``TrainTestSplit``, one per unique session.
    """
    unique_sessions = list(np.unique(dataset.session_ids))
    splits: list[TrainTestSplit] = []

    for test_session in unique_sessions:
        test_mask = dataset.session_ids == test_session
        train_mask = ~test_mask

        train_ds = ClassificationDataset(
            X=dataset.X[train_mask],
            y=dataset.y[train_mask],
            feature_names=dataset.feature_names,
            session_ids=dataset.session_ids[train_mask],
            stage_labels=dataset.stage_labels,
            epochs_df=dataset.epochs_df.loc[train_mask].reset_index(drop=True),
        )
        test_ds = ClassificationDataset(
            X=dataset.X[test_mask],
            y=dataset.y[test_mask],
            feature_names=dataset.feature_names,
            session_ids=dataset.session_ids[test_mask],
            stage_labels=dataset.stage_labels,
            epochs_df=dataset.epochs_df.loc[test_mask].reset_index(drop=True),
        )

        splits.append(TrainTestSplit(
            train=train_ds,
            test=test_ds,
            train_session_ids=sorted(set(unique_sessions) - {test_session}),
            test_session_ids=[test_session],
        ))

    return splits


def make_binary_labels(
    y: np.ndarray,
    positive_class: str = "remSleep",
) -> np.ndarray:
    """Convert multi-class labels to binary (1 = positive_class, 0 = rest).

    Args:
        y: Integer-encoded multi-class labels.
        positive_class: Stage name to treat as the positive class.

    Returns:
        Binary label array (same length as *y*).
    """
    positive_int = STAGE_TO_INT[positive_class]
    return (y == positive_int).astype(np.int64)


def generate_mock_dataset(
    n_sessions: int = 10,
    duration_hours: float = 4.0,
    base_seed: int = 100,
    min_coverage_pct: float = 0.0,
) -> ClassificationDataset:
    """Generate a multi-session mock dataset for testing.

    Creates *n_sessions* synthetic sleep sessions and runs them through
    the full preparation pipeline.

    Args:
        n_sessions: Number of mock nights to generate.
        duration_hours: Duration of each mock session.
        base_seed: Starting seed (incremented per session).
        min_coverage_pct: Quality gate threshold (0 = accept all).

    Returns:
        A ``ClassificationDataset`` with all sessions combined.
    """
    sessions = [
        generate_mock_session(duration_hours=duration_hours, seed=base_seed + i)
        for i in range(n_sessions)
    ]
    return prepare_sessions(sessions, min_coverage_pct=min_coverage_pct)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_dataset(df: pd.DataFrame) -> ClassificationDataset:
    """Extract X, y arrays from a combined epoch DataFrame."""
    # Get numeric feature columns (base + temporal), excluding metadata
    exclude = {
        "epoch_start", "epoch_end", "epoch_time_hours",
        "sleep_stage", "dominant_classification",
        "hr_count", "motion_count", "session_id",
    }
    feature_cols = [
        c for c in df.columns
        if c not in exclude and df[c].dtype in ("float64", "float32", "int64")
    ]

    X = df[feature_cols].values.astype(np.float64)
    y = df["sleep_stage"].map(STAGE_TO_INT).values.astype(np.int64)
    session_ids = df["session_id"].values

    return ClassificationDataset(
        X=X,
        y=y,
        feature_names=feature_cols,
        session_ids=session_ids,
        stage_labels=STAGE_LABELS,
        epochs_df=df,
    )
