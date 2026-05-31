"""Label ledger — provenance-scoped labels (commitment #17)."""
from __future__ import annotations

from .axes import DECLARED_TO_CANONICAL, canonical_axis
from .ledger import read_labels, record_label, record_labels
from .provenance import TRUST_ORDER, LabelSource, classify_source
from .query import group_by_source
from .record import LabelRecord

__all__ = [
    "LabelSource",
    "TRUST_ORDER",
    "classify_source",
    "LabelRecord",
    "record_label",
    "record_labels",
    "read_labels",
    "group_by_source",
    "canonical_axis",
    "DECLARED_TO_CANONICAL",
]
