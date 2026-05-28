"""L3 fusion layer — combines L2 FeatureSnapshots into per-axis BeliefState."""
from __future__ import annotations

from .belief_state import AxisEstimate, BeliefState
from .writer import write_axis_estimate

__all__ = ["AxisEstimate", "BeliefState", "write_axis_estimate"]
