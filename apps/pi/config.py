from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Hardcoded user id for v0 (single-user system).
AAKASH_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"

# Path to apps/inference (used to extend sys.path so we can import realtime/cue_decision/db).
INFERENCE_DIR = Path(__file__).resolve().parent.parent / "inference"


def ensure_inference_importable() -> None:
    """Make apps/inference modules importable from apps/pi code."""
    if str(INFERENCE_DIR) not in sys.path:
        sys.path.insert(0, str(INFERENCE_DIR))


@dataclass
class DaemonConfig:
    user_id: str = AAKASH_USER_ID
    epoch_seconds: int = 30
    predictor_tick_seconds: int = 30
    sensor_spec: list[str] = field(default_factory=lambda: ["mock"])
    cue_spec: list[str] = field(default_factory=lambda: ["stdout"])
    duration_minutes: int | None = None  # None = run until SIGINT
    mock_fast_forward: bool = False
    log_level: str = "INFO"

    def configure_logging(self) -> None:
        level = getattr(logging, self.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)-7s %(name)-20s %(message)s",
            datefmt="%H:%M:%S",
        )
