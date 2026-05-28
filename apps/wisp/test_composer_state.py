from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

APPS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS))
sys.path.insert(0, str(APPS / "inference"))

import wisp.composer as composer
from fusion.belief_state import AxisEstimate, BeliefState


def test_read_latest_state_drops_stale_axes(monkeypatch):
    now = datetime.now(timezone.utc)
    belief = BeliefState(user_id="u1")
    belief.update(AxisEstimate(
        axis="meta_context",
        value={"category": "waking/focused"},
        timestamp=now,
        confidence=0.9,
        source="L3.fusion.meta_context",
        meta_context="waking/focused",
        fresh_for_seconds=300,
    ))
    belief.update(AxisEstimate(
        axis="sleep_stage",
        value={"label": "rem"},
        timestamp=now - timedelta(hours=6),
        confidence=0.7,
        source="classifier.binary_rem",
        fresh_for_seconds=300,
    ))
    monkeypatch.setattr(composer, "load_belief_state", lambda user_id: belief)

    state = composer._read_latest_state("u1")
    assert state is not None
    assert "meta_context" in state
    assert "sleep_stage" not in state
    assert state["meta_context"]["value"] == {"category": "waking/focused"}


def test_read_latest_state_none_when_all_stale(monkeypatch):
    now = datetime.now(timezone.utc)
    belief = BeliefState(user_id="u1")
    belief.update(AxisEstimate(
        axis="meta_context",
        value={"category": "waking"},
        timestamp=now - timedelta(days=1),
        confidence=0.5,
        source="x",
        fresh_for_seconds=300,
    ))
    monkeypatch.setattr(composer, "load_belief_state", lambda user_id: belief)
    assert composer._read_latest_state("u1") is None
