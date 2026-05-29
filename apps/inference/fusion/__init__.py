"""L3 fusion layer — combines L2 FeatureSnapshots into per-axis BeliefState."""
from __future__ import annotations

from .belief_state import AxisEstimate, BeliefState

# `writer` (DB-backed) is intentionally NOT re-exported here: importing the pure
# BeliefState dataclasses must not pull db/psycopg into the import graph — the
# L1–L6 protocol core imports these. Import the writer explicitly where needed:
#     from fusion.writer import write_axis_estimate
__all__ = ["AxisEstimate", "BeliefState"]
