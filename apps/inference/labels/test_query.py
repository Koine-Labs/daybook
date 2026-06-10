"""Tests for the shared provenance-grouping helper (labels.group_by_source)."""
from __future__ import annotations

from datetime import datetime, timezone

from labels import LabelRecord, LabelSource, group_by_source


def _rec(source: LabelSource, value: float = 0.5) -> LabelRecord:
    return LabelRecord(
        user_id="u1",
        axis="arousal_inferred",
        value=value,
        source=source,
        observed_at=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
    )


def test_groups_records_by_source_tier() -> None:
    recs = [
        _rec(LabelSource.SELF_REPORT, 0.8),
        _rec(LabelSource.SELF_REPORT, 0.6),
        _rec(LabelSource.HEURISTIC, 0.3),
    ]
    grouped = group_by_source(recs)
    assert set(grouped) == {LabelSource.SELF_REPORT, LabelSource.HEURISTIC}
    assert len(grouped[LabelSource.SELF_REPORT]) == 2
    assert len(grouped[LabelSource.HEURISTIC]) == 1


def test_empty_input_returns_empty_dict() -> None:
    assert group_by_source([]) == {}


def test_preserves_record_order_within_a_tier() -> None:
    recs = [
        _rec(LabelSource.SELF_REPORT, 0.1),
        _rec(LabelSource.SELF_REPORT, 0.2),
        _rec(LabelSource.SELF_REPORT, 0.3),
    ]
    grouped = group_by_source(recs)
    assert [r.value for r in grouped[LabelSource.SELF_REPORT]] == [0.1, 0.2, 0.3]


def test_keys_are_labelsource_enums_not_strings() -> None:
    grouped = group_by_source([_rec(LabelSource.GROUND_TRUTH)])
    (key,) = grouped
    assert isinstance(key, LabelSource)
