"""Tests for meta_context axis fusion."""
from __future__ import annotations

from datetime import datetime, timezone

from fusion.axes.meta_context import classify_meta_context


def test_idle_long():
    out = classify_meta_context(active_app="Cursor", idle_seconds=400)
    assert out["category"] == "waking/idle"


def test_focused_coding():
    out = classify_meta_context(active_app="Cursor", idle_seconds=5)
    assert out["category"] == "waking/focused"


def test_communicating():
    out = classify_meta_context(active_app="Slack", idle_seconds=2)
    assert out["category"] == "waking/communicating"


def test_browsing():
    out = classify_meta_context(active_app="Arc", idle_seconds=10)
    assert out["category"] == "waking/browsing"


def test_consuming():
    out = classify_meta_context(active_app="YouTube", idle_seconds=15)
    assert out["category"] == "waking/consuming"


def test_other_falls_through():
    out = classify_meta_context(active_app="Finder", idle_seconds=2)
    assert out["category"] == "waking/other"
