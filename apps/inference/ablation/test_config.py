"""AblationConfig defaults, env overrides, frozen immutability — DB-free + LLM-free."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from ablation.config import AblationConfig, config_from_env


def test_defaults() -> None:
    cfg = AblationConfig()
    assert cfg.max_set_size == 3
    assert cfg.delta == 0.0
    assert cfg.min_labels == 8
    assert cfg.tol_window_s == 300
    assert cfg.promote_streak == 2
    assert cfg.split == "time_holdout"
    assert cfg.backend == "mac_scaffold"
    assert cfg.greedy is False


def test_frozen_immutable() -> None:
    cfg = AblationConfig()
    with pytest.raises(Exception):
        cfg.max_set_size = 5  # type: ignore[misc]


def test_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("ABLATION_BACKEND", "desktop_gpu")
    monkeypatch.setenv("ABLATION_MAX_SET_SIZE", "4")
    monkeypatch.setenv("ABLATION_DELTA", "0.05")
    monkeypatch.setenv("ABLATION_MIN_LABELS", "12")
    monkeypatch.setenv("ABLATION_TOL_WINDOW_S", "600")
    monkeypatch.setenv("ABLATION_PROMOTE_STREAK", "3")
    monkeypatch.setenv("ABLATION_GREEDY", "1")
    cfg = config_from_env()
    assert cfg.backend == "desktop_gpu"
    assert cfg.max_set_size == 4
    assert cfg.delta == 0.05
    assert cfg.min_labels == 12
    assert cfg.tol_window_s == 600
    assert cfg.promote_streak == 3
    assert cfg.greedy is True


def test_env_overrides_partial_keeps_defaults(monkeypatch) -> None:
    monkeypatch.delenv("ABLATION_BACKEND", raising=False)
    monkeypatch.setenv("ABLATION_MAX_SET_SIZE", "2")
    cfg = config_from_env()
    assert cfg.max_set_size == 2
    assert cfg.backend == "mac_scaffold"


def test_config_from_env_accepts_overrides_kwargs(monkeypatch) -> None:
    monkeypatch.delenv("ABLATION_MAX_SET_SIZE", raising=False)
    cfg = config_from_env(max_set_size=5)
    assert cfg.max_set_size == 5
