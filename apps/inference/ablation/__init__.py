"""Offline fusion-ablation harness (commitment #17 step #5, ARCHITECTURE §3 L3).

Enumerates candidate source sets, grades each against provenance-scoped ledger
labels, and promotes only the combinations that beat their best component. Reads
truth exclusively through the frozen `labels/` package (never forks it).
"""
from __future__ import annotations

from .config import DEFAULT_USER_ID, AblationConfig, config_from_env
from .source_sets import SourceSet, enumerate_candidates


def run_ablation(*args, **kwargs):
    """Lazy entrypoint — imports the orchestrator on call to keep import DB/LLM-free."""
    from .runner import run_ablation as _run

    return _run(*args, **kwargs)


def list_promoted(*args, **kwargs):
    """Lazy crash-safe read seam for live L3 fusers (returns [] when DB absent)."""
    from .store import list_promoted as _list

    return _list(*args, **kwargs)


__all__ = [
    "AblationConfig",
    "config_from_env",
    "DEFAULT_USER_ID",
    "SourceSet",
    "enumerate_candidates",
    "run_ablation",
    "list_promoted",
]
