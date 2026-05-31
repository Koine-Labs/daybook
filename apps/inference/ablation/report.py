"""Honest run report — manifest dict + markdown (A4: every dropped set, with reason)."""
from __future__ import annotations

from collections import Counter
from typing import Any

from .source_sets import SourceSet


def build_manifest(
    results_by_axis: dict[str, list],
    promoted: dict[str, list[SourceSet]],
) -> dict[str, Any]:
    """Per-axis: counts of tested vs dropped (by reason) + the dropped-set detail."""
    axes: dict[str, Any] = {}
    for axis, rows in results_by_axis.items():
        tested = [r for r in rows if r.dropped_reason is None]
        dropped_rows = [r for r in rows if r.dropped_reason is not None]
        reason_counts = Counter(r.dropped_reason for r in dropped_rows)
        axes[axis] = {
            "tested": len(tested),
            "dropped": dict(reason_counts),
            "dropped_sets": [
                {"source_set": list(r.source_set), "reason": r.dropped_reason}
                for r in dropped_rows
            ],
            "tested_sets": [
                {
                    "source_set": list(r.source_set),
                    "metrics": r.metrics,
                    "n_eval_pairs": r.n_eval_pairs,
                    "grader": r.grader,
                }
                for r in tested
            ],
            "promoted": [list(s) for s in promoted.get(axis, [])],
        }
    return {"axes": axes}


def render_markdown(
    results_by_axis: dict[str, list],
    promoted: dict[str, list[SourceSet]],
) -> str:
    """Markdown honesty surface: tested table + a Dropped section with every reason."""
    lines: list[str] = ["# Fusion-Ablation Report", ""]
    for axis, rows in results_by_axis.items():
        lines.append(f"## {axis}")
        lines.append("")
        tested = [r for r in rows if r.dropped_reason is None]
        lines.append("| source_set | metrics | n_eval | grader |")
        lines.append("|---|---|---|---|")
        for r in tested:
            metrics = ", ".join(f"{k}={v:.4f}" for k, v in r.metrics.items())
            lines.append(
                f"| {'+'.join(r.source_set)} | {metrics} | {r.n_eval_pairs} | {r.grader} |"
            )
        prom = promoted.get(axis, [])
        lines.append("")
        lines.append("**Promoted:** " + (", ".join("+".join(s) for s in prom) or "_none_"))
        lines.append("")
        dropped_rows = [r for r in rows if r.dropped_reason is not None]
        lines.append("### Dropped (not graded)")
        if not dropped_rows:
            lines.append("_none_")
        else:
            for r in dropped_rows:
                lines.append(f"- {'+'.join(r.source_set)} — {r.dropped_reason}")
        lines.append("")
    return "\n".join(lines)
