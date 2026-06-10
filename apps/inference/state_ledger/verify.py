"""Mechanical verifier — makes the manifest unable to lie about checkable facts."""
from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

from state_ledger.manifest import (BuildState, Capability, Manifest,
                                    Workstream, WorkstreamStatus, load_manifest)

INFERENCE_DIR = Path(__file__).resolve().parents[1]  # apps/inference


def check_imports(cap: Capability) -> list[str]:
    if cap.build_state is BuildState.ABSENT:
        return []
    out: list[str] = []
    for mod in cap.evidence.modules:
        try:
            importlib.import_module(mod)
        except Exception as e:  # import-time failure = the claim is false
            out.append(f"[{cap.id}] claims {cap.build_state.value} but module "
                       f"'{mod}' failed to import: {e!r}")
    return out


def check_markers(cap: Capability, root: Path = INFERENCE_DIR) -> list[str]:
    out: list[str] = []
    for m in cap.evidence.markers:
        path = root / m.path
        if not path.exists():
            out.append(f"[{cap.id}] marker path missing: {m.path}")
            continue
        found = m.pattern in path.read_text()
        if found != m.present:
            want = "present" if m.present else "absent"
            got = "present" if found else "absent"
            out.append(f"[{cap.id}] marker {m.pattern!r} expected {want} in "
                       f"{m.path} but was {got}")
    return out


def check_workstream_collisions(workstreams: list[Workstream]) -> list[str]:
    out: list[str] = []
    seen: dict[str, str] = {}
    for w in workstreams:
        if w.status is not WorkstreamStatus.IN_PROGRESS:
            continue
        for p in w.owns_paths:
            if p in seen:
                out.append(f"workstream collision on {p!r}: "
                           f"{seen[p]} and {w.id} are both in_progress")
            else:
                seen[p] = w.id
    return out


def check_test_count(expected: int, collected: int) -> list[str]:
    if collected != expected:
        return [f"test-count drift: manifest expects {expected}, collected "
                f"{collected}. If intentional, set expected_test_count: {collected}."]
    return []


def collect_test_count() -> int:
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "--co", "-q", "-p", "no:cacheprovider"],
        cwd=INFERENCE_DIR, capture_output=True, text=True, env=env,
    )
    m = re.search(r"(\d+)\s+tests?\s+collected", r.stdout)
    if not m:
        raise RuntimeError(f"could not parse collected test count from:\n{r.stdout[-2000:]}")
    return int(m.group(1))


def run(manifest: Manifest | None = None, *, collected: int | None = None) -> list[str]:
    manifest = manifest or load_manifest()
    violations: list[str] = []
    for cap in manifest.capabilities:
        violations += check_imports(cap)
        violations += check_markers(cap)
    violations += check_workstream_collisions(manifest.workstreams)
    if collected is None:
        collected = collect_test_count()
    violations += check_test_count(manifest.expected_test_count, collected)
    return violations


def main(argv: list[str] | None = None) -> int:
    violations = run()
    if violations:
        print("STATE LEDGER VERIFY: FAIL")
        for v in violations:
            print("  -", v)
        return 1
    print("STATE LEDGER VERIFY: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
