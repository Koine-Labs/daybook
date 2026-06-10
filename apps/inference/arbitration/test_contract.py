"""Ledger-contract conformance (DB-free): consume the frozen LabelRecord directly.

Proves arbitration consumes the frozen labels contract without a DB by feeding
hand-built LabelRecord fixtures (and a fake ledger.read_labels) through the path.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from labels import LabelRecord, LabelSource

from arbitration import blend, default_profile, summarize
from arbitration.constants import PERSONAL_TIERS, POPULATION_TIERS

NOW = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)


def test_personal_and_population_tier_sets_use_real_enum():
    # Reconciliation invariant: every tier is a real frozen LabelSource member,
    # and the two poles are disjoint.
    assert PERSONAL_TIERS == {
        LabelSource.SELF_REPORT, LabelSource.OBSERVED_OUTCOME, LabelSource.HEURISTIC
    }
    assert POPULATION_TIERS == {
        LabelSource.LITERATURE_PRIOR, LabelSource.DEMOGRAPHIC_PRIOR,
        LabelSource.LLM_LITERATURE_BOOTSTRAP,
    }
    assert PERSONAL_TIERS.isdisjoint(POPULATION_TIERS)


def test_consumes_hand_built_labelrecords_without_db():
    rows = [
        LabelRecord(user_id="u", axis="arousal", value=0.5,
                    source=LabelSource.SELF_REPORT, observed_at=NOW, confidence=0.9),
        LabelRecord(user_id="u", axis="arousal", value=0.3,
                    source=LabelSource.LITERATURE_PRIOR, observed_at=NOW, confidence=1.0),
    ]
    ev = summarize(rows, default_profile("arousal"), now=NOW)
    # literature row excluded; self_report counted.
    assert set(ev) == {LabelSource.SELF_REPORT.value}
    res = blend("arousal", ev, default_profile("arousal"), 0.0, 1.0, now=NOW)
    assert 0.0 < res.w_personal < 1.0


def test_fake_read_labels_drives_summarize():
    def fake_read_labels(user_id, *, axis=None, sources=None, **kw):
        return [
            LabelRecord(user_id=user_id, axis=axis or "arousal", value=0.5,
                        source=LabelSource.OBSERVED_OUTCOME, observed_at=NOW, confidence=1.0)
        ]

    rows = fake_read_labels("u", axis="arousal", sources=[LabelSource.OBSERVED_OUTCOME.value])
    ev = summarize(rows, default_profile("arousal"), now=NOW)
    assert ev[LabelSource.OBSERVED_OUTCOME.value].count == 1


def test_unknown_source_string_normalizes_via_labelrecord():
    # LabelRecord.__post_init__ coerces a string source to the enum; off-taxonomy
    # strings raise ValueError there (frozen contract), so summarize only ever sees
    # real enum members. Confirm a valid string is accepted.
    rec = LabelRecord(user_id="u", axis="arousal", value=0.5,
                      source="self_report", observed_at=NOW, confidence=1.0)
    assert rec.source is LabelSource.SELF_REPORT
    ev = summarize([rec], default_profile("arousal"), now=NOW)
    assert set(ev) == {LabelSource.SELF_REPORT.value}
