"""Renderer — generates all human-facing surfaces from the manifest."""
from __future__ import annotations

import json
from pathlib import Path

from state_ledger.manifest import Capability, Manifest, load_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
STATUS_PATH = REPO_ROOT / "docs" / "STATUS.md"
STATE_JSON_PATH = REPO_ROOT / "docs" / "state" / "state.json"

BEGIN = "<!-- STATE:BEGIN -->"
END = "<!-- STATE:END -->"


def render_status_block(m: Manifest) -> str:
    lines = [
        BEGIN,
        "",
        "## Current state (generated — do not edit by hand)",
        "",
        f"_Generated from `docs/state/`. {len(m.capabilities)} capabilities tracked; "
        f"suite expects {m.expected_test_count} tests._",
        "",
        "| Capability | Build state | Alignment | % | Serves |",
        "|---|---|---|---:|---|",
    ]
    for c in m.capabilities:
        serves = ", ".join(c.serves_pillars) or "—"
        lines.append(f"| {c.name} | {c.build_state.value} | {c.alignment.value} "
                     f"| {c.percent_done} | {serves} |")
    lines += ["", END]
    return "\n".join(lines)


def splice_status(existing: str, block: str) -> str:
    if BEGIN in existing and END in existing:
        pre = existing.split(BEGIN, 1)[0]
        post = existing.split(END, 1)[1]
        return pre + block + post
    # No markers yet: insert after the first line (the H1), else prepend.
    parts = existing.split("\n", 1)
    if len(parts) == 2:
        return parts[0] + "\n\n" + block + "\n\n" + parts[1]
    return block + "\n\n" + existing


def _cap_dict(c: Capability) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "serves_pillars": c.serves_pillars,
        "serves_commitments": c.serves_commitments,
        "build_state": c.build_state.value,
        "alignment": c.alignment.value,
        "percent_done": c.percent_done,
        "gaps": c.gaps,
    }


def render_state_json(m: Manifest) -> dict:
    return {
        "pillars": [vars(p) for p in m.pillars],
        "commitments": [vars(c) for c in m.commitments],
        "capabilities": [_cap_dict(c) for c in m.capabilities],
        "workstreams": [
            {"id": w.id, "title": w.title, "status": w.status.value,
             "owns_paths": w.owns_paths, "touches_commitments": w.touches_commitments,
             "github_issue": w.github_issue}
            for w in m.workstreams
        ],
        "expected_test_count": m.expected_test_count,
    }


def main(argv: list[str] | None = None) -> int:
    m = load_manifest()
    block = render_status_block(m)
    existing = STATUS_PATH.read_text()
    STATUS_PATH.write_text(splice_status(existing, block))
    STATE_JSON_PATH.write_text(json.dumps(render_state_json(m), indent=2) + "\n")
    print(f"rendered: {STATUS_PATH.name} block + {STATE_JSON_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
