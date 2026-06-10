"""Candidate enumeration — power-set, canonical sort, max_set_size cap, greedy."""
from __future__ import annotations

import sys
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from ablation.config import AblationConfig
from ablation.source_sets import canonical, enumerate_candidates


def test_canonical_sorts_and_dedups() -> None:
    assert canonical(["eog", "eeg", "eog"]) == ("eeg", "eog")
    assert canonical(["MIC", "Eeg"]) == ("eeg", "mic")


def test_power_set_correctness_small() -> None:
    cfg = AblationConfig(max_set_size=3)
    cands, dropped = enumerate_candidates(["eeg", "eog"], cfg)
    # non-empty subsets of {eeg,eog}: {eeg},{eog},{eeg,eog}
    assert set(cands) == {("eeg",), ("eog",), ("eeg", "eog")}
    assert dropped == []


def test_canonical_ordering_of_candidates() -> None:
    cfg = AblationConfig(max_set_size=3)
    cands, _ = enumerate_candidates(["eog", "eeg"], cfg)
    for s in cands:
        assert list(s) == sorted(s)


def test_max_set_size_cap_returns_dropped_with_reason() -> None:
    cfg = AblationConfig(max_set_size=2)
    cands, dropped = enumerate_candidates(["eeg", "eog", "mic"], cfg)
    # size-1 and size-2 are candidates; the full size-3 set is dropped (capped)
    assert ("eeg", "eog", "mic") not in cands
    assert all(len(s) <= 2 for s in cands)
    dropped_sets = {s for s, _ in dropped}
    assert ("eeg", "eog", "mic") in dropped_sets
    for s, reason in dropped:
        assert reason == "capped_by_max_set_size"


def test_no_silent_caps_every_oversized_set_reported() -> None:
    cfg = AblationConfig(max_set_size=1)
    cands, dropped = enumerate_candidates(["a", "b", "c"], cfg)
    assert set(cands) == {("a",), ("b",), ("c",)}
    dropped_sets = {s for s, _ in dropped}
    # all size-2 and size-3 subsets must be reported as dropped
    assert ("a", "b") in dropped_sets
    assert ("a", "c") in dropped_sets
    assert ("b", "c") in dropped_sets
    assert ("a", "b", "c") in dropped_sets


def test_empty_available_sources() -> None:
    cfg = AblationConfig()
    cands, dropped = enumerate_candidates([], cfg)
    assert cands == []
    assert dropped == []


def test_greedy_mode_returns_forward_selection_path() -> None:
    cfg = AblationConfig(max_set_size=3, greedy=True)
    cands, dropped = enumerate_candidates(["eeg", "eog", "mic", "vision"], cfg)
    # greedy path: each singleton, plus a growing chain up to max_set_size.
    # sizes present should be 1..max_set_size and the count is linear, not 2^n.
    sizes = sorted({len(s) for s in cands})
    assert sizes == [1, 2, 3]
    # forward selection is far smaller than the full power set (2^4-1=15)
    assert len(cands) < 15
    # everything canonical + unique
    assert len(set(cands)) == len(cands)
