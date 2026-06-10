"""Backends — MacScaffold deterministic fit/reconstruct; DesktopGPU slot raises."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from labels import LabelSource
from ablation.dataset import GradedPair
from ablation.backend import DesktopGPUBackend, MacScaffoldBackend, get_backend

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _pair(value: float, inputs: dict) -> GradedPair:
    return GradedPair(
        observed_at=_T0,
        truth_value=value,
        truth_source=LabelSource.SELF_REPORT,
        truth_confidence=0.9,
        belief_inputs=inputs,
    )


def test_mac_backend_fit_deterministic() -> None:
    b = MacScaffoldBackend()
    train = [_pair(0.2, {"eeg": 0.2}), _pair(0.8, {"eeg": 0.8})]
    p1 = b.fit("arousal_inferred", ("eeg",), train)
    p2 = b.fit("arousal_inferred", ("eeg",), train)
    assert p1 == p2


def test_mac_backend_reconstruct_tracks_input() -> None:
    b = MacScaffoldBackend()
    # truth == input exactly -> fitted reconstruction should track input
    train = [_pair(0.1, {"eeg": 0.1}), _pair(0.9, {"eeg": 0.9})]
    params = b.fit("arousal_inferred", ("eeg",), train)
    lo = b.reconstruct_belief("arousal_inferred", ("eeg",), _pair(0.1, {"eeg": 0.1}), params)
    hi = b.reconstruct_belief("arousal_inferred", ("eeg",), _pair(0.9, {"eeg": 0.9}), params)
    assert lo < hi


def test_mac_backend_multi_source_average() -> None:
    b = MacScaffoldBackend()
    train = [_pair(0.5, {"eeg": 0.5, "eog": 0.5})]
    params = b.fit("arousal_inferred", ("eeg", "eog"), train)
    out = b.reconstruct_belief(
        "arousal_inferred", ("eeg", "eog"), _pair(0.5, {"eeg": 0.4, "eog": 0.6}), params
    )
    assert 0.0 <= out <= 1.0


def test_mac_backend_missing_source_uses_neutral() -> None:
    b = MacScaffoldBackend()
    train = [_pair(0.5, {"eeg": 0.5})]
    params = b.fit("arousal_inferred", ("eeg",), train)
    # pair lacking the source -> reconstruct must not crash
    out = b.reconstruct_belief("arousal_inferred", ("eeg",), _pair(0.5, {}), params)
    assert isinstance(out, float)


def test_desktop_backend_slot_raises() -> None:
    b = DesktopGPUBackend()
    with pytest.raises(NotImplementedError):
        b.fit("arousal_inferred", ("eeg",), [])


def test_get_backend_selects() -> None:
    assert isinstance(get_backend("mac_scaffold"), MacScaffoldBackend)
    assert isinstance(get_backend("desktop_gpu"), DesktopGPUBackend)
    with pytest.raises(ValueError):
        get_backend("nonsense")
