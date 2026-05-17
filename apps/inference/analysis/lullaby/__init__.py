"""
Lullaby Sleep Data Analysis Toolkit.

Python package for loading, analyzing, and visualizing sleep session data
exported from the Lullaby iOS/watchOS app.
"""

__version__ = "0.2.0"

from lullaby.loader import SleepSessionData, load_session, load_all_sessions, generate_mock_session
from lullaby.features import align_to_epochs
from lullaby.visualization import plot_night_overview, plot_feature_distributions, plot_epoch_heatmap
from lullaby.statistics import compare_rem_vs_non_rem, compute_correlations, stage_transition_analysis
from lullaby.quality import assess_quality, print_quality_report

# Phase 2: Classification pipeline
from lullaby.temporal_features import add_temporal_features, TemporalFeatureConfig
from lullaby.pipeline import (
    ClassificationDataset, TrainTestSplit,
    prepare_sessions, split_by_session, get_leave_one_out_splits,
    make_binary_labels, generate_mock_dataset,
    STAGE_LABELS, STAGE_TO_INT, INT_TO_STAGE,
)
from lullaby.model import (
    XGBConfig, TrainedModel, CVResult,
    train_multiclass, train_binary_rem, cross_validate, tune_hyperparameters,
)
from lullaby.evaluation import (
    ClassificationMetrics, SuccessCriteria,
    compute_metrics, compute_rem_onset_latency, check_success_criteria,
    predict, print_metrics_report,
    plot_confusion_matrix, plot_hypnogram_comparison,
    plot_feature_importance, plot_shap_summary, plot_cv_results,
)
from lullaby.export import save_model, load_model, export_coreml
