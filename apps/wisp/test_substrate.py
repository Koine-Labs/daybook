from __future__ import annotations

import sys
from pathlib import Path

APPS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS))
sys.path.insert(0, str(APPS / "inference"))

import wisp.composer as composer


def test_gather_substrate_populates_observations_and_traits(monkeypatch):
    monkeypatch.setattr(composer, "_read_recent_observations",
                        lambda user_id, limit: [{"content": "prefers brevity"}])
    monkeypatch.setattr(composer, "_read_current_traits",
                        lambda user_id: {"warmth": 0.6, "dryness": 0.7})
    monkeypatch.setattr(composer, "_read_latest_state",
                        lambda user_id: {"meta_context": {"value": {"category": "waking/focused"}}})

    ctx = composer.gather_substrate(user_id="u1")

    assert ctx.relevant_observations == [{"content": "prefers brevity"}]
    assert ctx.regis_traits == {"warmth": 0.6, "dryness": 0.7}
    assert ctx.current_user_state == {"meta_context": {"value": {"category": "waking/focused"}}}


def test_gather_substrate_tolerates_empty(monkeypatch):
    monkeypatch.setattr(composer, "_read_recent_observations", lambda user_id, limit: [])
    monkeypatch.setattr(composer, "_read_current_traits", lambda user_id: {})
    monkeypatch.setattr(composer, "_read_latest_state", lambda user_id: None)
    ctx = composer.gather_substrate(user_id="u1")
    assert ctx.relevant_observations == []
    assert ctx.regis_traits == {}
    assert ctx.current_user_state is None
