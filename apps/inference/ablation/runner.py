"""Orchestrator — open run → evaluate each axis → decide promotions → report → close.

`open_run`/`close_run`/`write_results`/`write_promotions` are module-level names so
tests monkeypatch the DB writes. The whole flow is crash-safe: a missing DB yields
None ids and 0 write counts but the evaluation + report still complete in memory.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from .backend import get_backend
from .config import DEFAULT_USER_ID, AblationConfig
from .evaluate import evaluate_axis
from .promote import decide_promotions, decisions_to_rows
from .report import build_manifest, render_markdown
from .store import close_run, open_run, write_promotions, write_results

logger = logging.getLogger(__name__)

_PROMOTE_METRIC = "brier"


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(INF_DIR), capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001 — provenance is best-effort
        return None


def run_ablation(
    user_id: str = DEFAULT_USER_ID,
    axes: list[str] | None = None,
    cfg: AblationConfig | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the harness over `axes`; return {manifest, markdown, run_id, promoted}."""
    cfg = cfg or AblationConfig()
    axes = axes or ["arousal_inferred"]
    backend = get_backend(cfg.backend)

    run_id = open_run(
        user_id, backend=cfg.backend, axes=axes, config=asdict(cfg), git_sha=_git_sha()
    ) or "in-memory-run"

    results_by_axis: dict[str, list] = {}
    promoted_by_axis: dict[str, list[tuple[str, ...]]] = {}

    for axis in axes:
        rows = evaluate_axis(user_id, axis, cfg, backend, run_id)
        results_by_axis[axis] = rows
        if not dry_run:
            write_results(rows)
        decisions = decide_promotions(
            rows, cfg, user_id, axis, run_id, metric=_PROMOTE_METRIC
        )
        promoted_by_axis[axis] = [d.source_set for d in decisions if d.status == "promoted"]
        if not dry_run and decisions:
            write_promotions(decisions_to_rows(decisions, user_id, axis, run_id))

    manifest = build_manifest(results_by_axis, promoted_by_axis)
    markdown = render_markdown(results_by_axis, promoted_by_axis)
    if not dry_run:
        close_run(run_id, status="complete", manifest=manifest)

    return {
        "run_id": run_id,
        "manifest": manifest,
        "markdown": markdown,
        "promoted": promoted_by_axis,
    }
