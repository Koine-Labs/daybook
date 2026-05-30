from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labels.provenance import LabelSource
from labels.record import LabelRecord


def _rec() -> LabelRecord:
    return LabelRecord(
        user_id="61c18d4c-1c20-408a-bd5f-f5f88fd9922f",
        axis="fatigue",
        value=0.8,
        source=LabelSource.SELF_REPORT,
        observed_at=datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
        confidence=0.9,
        provenance={"declaration_text": "wiped but wired", "classifier": "quickpick"},
        consent_scope="self_report_v1",
        meta_context="waking",
    )


def test_to_row_round_trip_matches_insert_column_order():
    rec = _rec()
    row = rec.to_row()
    assert row == (
        rec.user_id,
        rec.axis,
        rec.value,
        rec.confidence,
        rec.source.value,
        rec.provenance,
        rec.consent_scope,
        rec.i_model_id,
        rec.meta_context,
        rec.observed_at,
    )
    assert row[4] == "self_report"


def test_defaults_are_applied():
    rec = LabelRecord(
        user_id="u",
        axis="arousal",
        value="high",
        source=LabelSource.HEURISTIC,
        observed_at=datetime.now(timezone.utc),
    )
    assert rec.confidence == 0.5
    assert rec.provenance == {}
    assert rec.consent_scope == "unscoped_v0"
    assert rec.i_model_id is None
    assert rec.meta_context is None


def test_string_source_is_coerced_to_enum():
    rec = LabelRecord(
        user_id="u",
        axis="arousal",
        value=1,
        source="self_report",
        observed_at=datetime.now(timezone.utc),
    )
    assert rec.source is LabelSource.SELF_REPORT


def test_naive_observed_at_rejected():
    with pytest.raises(ValueError):
        LabelRecord(
            user_id="u",
            axis="arousal",
            value=1,
            source=LabelSource.SELF_REPORT,
            observed_at=datetime(2026, 5, 30, 12, 0),
        )
