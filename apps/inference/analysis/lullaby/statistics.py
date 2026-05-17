"""
Statistical analysis for Lullaby sleep data.

Compares sensor features between REM and non-REM epochs using
non-parametric tests, computes correlations, and analyzes sleep
stage transitions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from lullaby.features import get_feature_columns


# ---------------------------------------------------------------------------
# REM vs Non-REM comparison
# ---------------------------------------------------------------------------

def compare_rem_vs_non_rem(
    epochs: pd.DataFrame,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Compare each numeric feature between REM and non-REM epochs.

    Uses Mann-Whitney U test (non-parametric, robust to non-normal
    distributions typical in physiological data).

    Args:
        epochs: Epoch-aligned feature DataFrame with 'sleep_stage' column.
        alpha: Significance threshold before correction.

    Returns:
        DataFrame with columns: feature, rem_median, non_rem_median,
        u_statistic, p_value, p_corrected, effect_size, cohens_d, significant.
        Sorted by p_value ascending.
    """
    features = get_feature_columns(epochs)

    # Split into REM vs non-REM (excluding awake and inBed for cleaner comparison)
    rem_mask = epochs["sleep_stage"] == "remSleep"
    non_rem_mask = epochs["sleep_stage"].isin(["coreLight", "deepSleep"])

    rem = epochs[rem_mask]
    non_rem = epochs[non_rem_mask]

    if rem.empty or non_rem.empty:
        return pd.DataFrame(columns=[
            "feature", "rem_median", "non_rem_median", "u_statistic",
            "p_value", "p_corrected", "effect_size", "cohens_d", "significant",
        ])

    results = []
    n_tests = len(features)

    for feat in features:
        rem_vals = rem[feat].dropna()
        non_rem_vals = non_rem[feat].dropna()

        if len(rem_vals) < 3 or len(non_rem_vals) < 3:
            continue

        # Mann-Whitney U test
        u_stat, p_value = stats.mannwhitneyu(
            rem_vals, non_rem_vals, alternative="two-sided"
        )

        # Rank-biserial correlation (effect size for Mann-Whitney)
        n1, n2 = len(rem_vals), len(non_rem_vals)
        effect_size = 1 - (2 * u_stat) / (n1 * n2)

        # Cohen's d for interpretability
        pooled_std = np.sqrt(
            ((len(rem_vals) - 1) * rem_vals.std()**2 +
             (len(non_rem_vals) - 1) * non_rem_vals.std()**2) /
            (len(rem_vals) + len(non_rem_vals) - 2)
        )
        cohens_d = (rem_vals.mean() - non_rem_vals.mean()) / pooled_std if pooled_std > 0 else 0

        # Bonferroni correction
        p_corrected = min(p_value * n_tests, 1.0)

        results.append({
            "feature": feat,
            "rem_median": rem_vals.median(),
            "non_rem_median": non_rem_vals.median(),
            "rem_n": len(rem_vals),
            "non_rem_n": len(non_rem_vals),
            "u_statistic": u_stat,
            "p_value": p_value,
            "p_corrected": p_corrected,
            "effect_size": round(effect_size, 4),
            "cohens_d": round(cohens_d, 4),
            "significant": p_corrected < alpha,
        })

    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df = result_df.sort_values("p_value").reset_index(drop=True)
    return result_df


# ---------------------------------------------------------------------------
# Correlation analysis
# ---------------------------------------------------------------------------

def compute_correlations(
    epochs: pd.DataFrame,
    method: str = "spearman",
) -> pd.DataFrame:
    """Compute correlation matrix between all numeric features.

    Args:
        epochs: Epoch-aligned feature DataFrame.
        method: 'pearson' or 'spearman' (default spearman for robustness).

    Returns:
        Correlation matrix DataFrame.
    """
    features = get_feature_columns(epochs)
    return epochs[features].corr(method=method)


# ---------------------------------------------------------------------------
# Stage transition analysis
# ---------------------------------------------------------------------------

def stage_transition_analysis(
    epochs: pd.DataFrame,
) -> dict:
    """Analyze sleep stage transitions and pre-REM feature patterns.

    Returns:
        Dictionary with:
        - 'transition_matrix': DataFrame of transition probabilities
        - 'transition_counts': DataFrame of raw transition counts
        - 'pre_rem_features': DataFrame of mean features in 2 epochs before REM onset
        - 'post_rem_features': DataFrame of mean features in 2 epochs after REM onset
        - 'rem_onset_count': Number of REM onset events found
    """
    valid = epochs[epochs["sleep_stage"].notna()].copy()
    stages = valid["sleep_stage"].values
    features = get_feature_columns(valid)

    result = {
        "transition_matrix": pd.DataFrame(),
        "transition_counts": pd.DataFrame(),
        "pre_rem_features": pd.DataFrame(),
        "post_rem_features": pd.DataFrame(),
        "rem_onset_count": 0,
    }

    if len(stages) < 2:
        return result

    # --- Transition matrix ---
    unique_stages = sorted(set(stages))
    counts = pd.DataFrame(0, index=unique_stages, columns=unique_stages)

    for i in range(len(stages) - 1):
        from_stage = stages[i]
        to_stage = stages[i + 1]
        counts.loc[from_stage, to_stage] += 1

    result["transition_counts"] = counts

    # Normalize to probabilities
    row_sums = counts.sum(axis=1)
    probs = counts.div(row_sums, axis=0).fillna(0)
    result["transition_matrix"] = probs.round(3)

    # --- Pre/post REM onset feature analysis ---
    # Find indices where REM starts (transition into REM)
    rem_onsets = []
    for i in range(1, len(stages)):
        if stages[i] == "remSleep" and stages[i - 1] != "remSleep":
            rem_onsets.append(i)

    result["rem_onset_count"] = len(rem_onsets)

    if rem_onsets and features:
        # Collect features from 2 epochs before and after each REM onset
        pre_rows = []
        post_rows = []

        for onset_idx in rem_onsets:
            # Pre-REM: 2 epochs before onset
            for offset in [-2, -1]:
                idx = onset_idx + offset
                if 0 <= idx < len(valid):
                    pre_rows.append(valid.iloc[idx][features])

            # Post-REM: first 2 epochs of REM
            for offset in [0, 1]:
                idx = onset_idx + offset
                if idx < len(valid) and valid.iloc[idx]["sleep_stage"] == "remSleep":
                    post_rows.append(valid.iloc[idx][features])

        if pre_rows:
            result["pre_rem_features"] = pd.DataFrame(pre_rows).mean().to_frame("mean").T
        if post_rows:
            result["post_rem_features"] = pd.DataFrame(post_rows).mean().to_frame("mean").T

    return result


def format_statistics_table(stats_df: pd.DataFrame) -> str:
    """Format the REM vs non-REM comparison table for display.

    Args:
        stats_df: Output from compare_rem_vs_non_rem().

    Returns:
        Formatted string table.
    """
    if stats_df.empty:
        return "No statistical comparisons available (need both REM and non-REM epochs)."

    lines = [
        f"{'Feature':<30} {'REM Med':>9} {'NonREM Med':>11} "
        f"{'p-value':>10} {'p-corr':>10} {'Effect':>8} {'Cohen d':>9} {'Sig':>5}",
        "-" * 100,
    ]

    for _, row in stats_df.iterrows():
        sig_marker = "***" if row["significant"] else ""
        p_str = f"{row['p_value']:.2e}" if row["p_value"] < 0.001 else f"{row['p_value']:.4f}"
        pc_str = f"{row['p_corrected']:.2e}" if row["p_corrected"] < 0.001 else f"{row['p_corrected']:.4f}"
        lines.append(
            f"{row['feature']:<30} {row['rem_median']:>9.2f} {row['non_rem_median']:>11.2f} "
            f"{p_str:>10} {pc_str:>10} {row['effect_size']:>8.3f} {row['cohens_d']:>9.3f} {sig_marker:>5}"
        )

    return "\n".join(lines)
