"""FeatureSnapshot — uniform envelope produced by every L2 feature extractor.

Per ARCHITECTURE.md §3 L2: every modality's L2 output is a FeatureSnapshot
with a uniform envelope (timestamp, source, modality, confidence) and a
modality-specific payload (JSONB-shaped dict).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FeatureSnapshot:
    """One L2 feature-extraction output, ready for L3 fusion."""

    user_id: str
    timestamp: datetime               # tz-aware UTC
    modality: str                     # 'biometric' | 'audio' | 'mac' | 'eeg' | 'cam' | 'derived'
    source: str                       # e.g., 'watch.hr_30s', 'mac.app_activity'
    payload: dict[str, Any]           # modality-specific feature dict
    confidence: float | None = None   # [0, 1] if computable
    duration_ms: int | None = None    # observation window length
    meta_context_hint: str | None = None  # e.g., 'waking' if known at L2
    i_model_id: str | None = None     # commitment #1

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("FeatureSnapshot.timestamp must be tz-aware UTC")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")

    def to_dict(self) -> dict[str, Any]:
        """Serializable dict (timestamp → ISO string)."""
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d
