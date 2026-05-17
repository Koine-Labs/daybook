"""Generate a test XGBoost model from mock data for inference server testing."""

from __future__ import annotations

import sys
from pathlib import Path

# Add analysis package to path
_analysis_dir = Path(__file__).resolve().parent.parent / "analysis"
sys.path.insert(0, str(_analysis_dir))

from lullaby.loader import generate_mock_session
from lullaby.pipeline import prepare_sessions
from lullaby.model import train_multiclass
from lullaby.export import save_model


def main() -> None:
    output_dir = Path(__file__).parent / "models"
    output_dir.mkdir(exist_ok=True)

    # Generate 3 mock sessions for minimal training
    sessions = [generate_mock_session(duration_hours=4.0, seed=i) for i in range(3)]

    # Run through the pipeline
    dataset = prepare_sessions(sessions, min_coverage_pct=0.0)

    # Train 5-class model
    model = train_multiclass(dataset)

    # Export
    save_model(model, output_dir, version="test-0.1.0")
    print(f"Model saved to {output_dir}")
    print(f"Features: {len(dataset.feature_names)}")
    print(f"Files: {list(output_dir.iterdir())}")


if __name__ == "__main__":
    main()
