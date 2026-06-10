"""Shared, pure helpers over LabelRecord sequences (no DB, no LLM).

The single provenance-grouping primitive the #17 back-half consumers reuse:
cold-start arbitration (#4) tier-weights each group; the fusion-ablation grader
(#5) ranks groups by TRUST_ORDER. Both start from this grouping instead of each
re-implementing a groupby over `read_labels(...)` output.
"""
from __future__ import annotations

from typing import Iterable

from .provenance import LabelSource
from .record import LabelRecord


def group_by_source(records: Iterable[LabelRecord]) -> dict[LabelSource, list[LabelRecord]]:
    """Group labels by their LabelSource tier, preserving per-tier input order."""
    grouped: dict[LabelSource, list[LabelRecord]] = {}
    for rec in records:
        grouped.setdefault(rec.source, []).append(rec)
    return grouped
