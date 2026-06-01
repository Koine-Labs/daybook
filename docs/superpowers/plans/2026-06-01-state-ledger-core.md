# State Ledger Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the anti-drift core of the Daybook State Ledger — a machine-readable manifest, a mechanical CI verifier that makes the manifest unable to lie, and a renderer that generates the STATUS.md current-state block + a `state.json` dashboard feed.

**Architecture:** A manifest in `docs/state/*.yaml` is the single source of truth. Python tooling under `apps/inference/state_ledger/` loads it (`manifest.py`), verifies its mechanical claims against the repo (`verify.py`), and renders human-facing outputs from it (`render.py`). CI runs the verifier on every PR. The dashboard UI, Cloudflare hosting, and the AI auditor are deliberately deferred to follow-on plans — this plan delivers working anti-drift on its own.

**Tech Stack:** Python 3.11, `pyyaml` 6.0.3 (already installed), pytest (DB-free, the established CI mode), GitHub Actions.

**Conventions (from CLAUDE.md):** `from __future__ import annotations`; full type hints; `pathlib.Path`; one-line docstrings; tz-aware UTC if dates appear. Tests are `test_*.py` inside the package dir (matches `core/`, `fusion/`, etc.). All commands run from `apps/inference` with `.venv` active and `DATABASE_URL` unset.

---

## File Structure

| File | Responsibility |
|---|---|
| `docs/state/pillars.yaml` | Vision pillars + the 16 architectural commitments (strategic targets) |
| `docs/state/capabilities.yaml` | `expected_test_count` + each real capability with build_state/alignment/%/gaps/evidence |
| `docs/state/workstreams.yaml` | Active/planned parallel efforts with `owns_paths` for collision detection |
| `docs/state/README.md` | How the ledger works: "edit the manifest, never the generated outputs" |
| `apps/inference/state_ledger/__init__.py` | Package marker |
| `apps/inference/state_ledger/manifest.py` | Dataclasses + enums + YAML loader/validator |
| `apps/inference/state_ledger/verify.py` | Mechanical verifier: imports, markers, collisions, test-count |
| `apps/inference/state_ledger/render.py` | Renders STATUS.md block + state.json from the manifest |
| `apps/inference/state_ledger/test_manifest.py` | Loader/validation tests |
| `apps/inference/state_ledger/test_verify.py` | Verifier tests (synthetic temp manifest) |
| `apps/inference/state_ledger/test_render.py` | Renderer idempotency + splice tests |
| `.github/workflows/state-verify.yml` | Per-PR: run verifier + render-staleness check |

---

## Task 1: Package skeleton + seed manifest data

**Files:**
- Create: `apps/inference/state_ledger/__init__.py`
- Create: `docs/state/pillars.yaml`
- Create: `docs/state/capabilities.yaml`
- Create: `docs/state/workstreams.yaml`

- [ ] **Step 1: Create the package marker**

Create `apps/inference/state_ledger/__init__.py`:

```python
"""Daybook State Ledger — manifest-driven, drift-proof project state."""
```

- [ ] **Step 2: Seed `docs/state/pillars.yaml`**

Content (vision pillars from the 2026-06-01 audit + the 16 commitments from CLAUDE.md):

```yaml
vision_pillars:
  - {id: multimodal_fusion, name: "Always-on multimodal sensing fused into one live state", description: "Voice/text/gesture/biometric/audio/vision/BCI fused into a per-axis BeliefState", centrality: high}
  - {id: semantic_first, name: "Semantic-first privacy (extract meaning, discard raw)", description: "Continuous low-bandwidth extraction; raw discarded; cloud only as escalation", centrality: high}
  - {id: jepa_prediction, name: "Prediction in latent space (JEPA world model)", description: "Encoder + action-conditioned predictor + SIGReg + CEM (LeWM recipe)", centrality: high}
  - {id: learned_decisions, name: "Outcome-driven learned action selection", description: "Thompson bandit -> CEM; Regis as causally-modeled controlled variable", centrality: high}
  - {id: regis_character, name: "Persistent dual-mode generative Regis", description: "Witness asleep / Companion awake; PERSONA.md as system prompt", centrality: high}
  - {id: i_models, name: "Three self-discovered I-Models", description: "user_self / regis_of_user / regis_self emerging via clustering", centrality: high}
  - {id: meta_context, name: "Meta-context biases every layer", description: "Waking/Sleep + sub-contexts condition L2-L6", centrality: high}
  - {id: distributed_topology, name: "Pi/ESP32 satellites -> Mac inference hub", description: "NetworkTransport relay is the keystone", centrality: high}
  - {id: voice_first, name: "Voice-first interface", description: "Audio/bone-conduction TTS primary; screens debug-only", centrality: high}
  - {id: fastapi_seam, name: "Native clients talk only to FastAPI bridge", description: "HTTP seam is the platform/language boundary", centrality: medium}
  - {id: sleep_wedge, name: "Sleep/dream-recall validation wedge", description: "Deferred but active; sleep biometrics collected throughout", centrality: high}
  - {id: continuous_build, name: "Continuous build (v1 IS the v3 substrate)", description: "Build endpoint features now even when hardware lags", centrality: high}
  - {id: provenance_labels, name: "Labels are provenance-scoped priors, not truth", description: "Literature/LLM/demographic bootstrap; personal evidence supersedes", centrality: medium}
  - {id: personal_model_moat, name: "Moat = longitudinal personal model x speed x ecosystem-agnostic", description: "Hardware is fungible; the model on your data is not", centrality: high}

commitments:
  - {id: 1, title: "I-Model polymorphism", rule_summary: "Every event entity has i_model_id UUID NULL"}
  - {id: 2, title: "Content polymorphism", rule_summary: "regis_moments.kind is a pluggable discriminator"}
  - {id: 3, title: "Wisp-as-interface", rule_summary: "Audio output is the primary surface"}
  - {id: 4, title: "Three distinct I-Models", rule_summary: "user_self + regis_of_user + regis_self"}
  - {id: 5, title: "Regis is dual-mode", rule_summary: "Witness during sleep / Companion when awake"}
  - {id: 6, title: "Self-expanding I-Models", rule_summary: "I-Models discovered via clustering, not pre-defined"}
  - {id: 7, title: "Moment polymorphism", rule_summary: "regis_moments is the generalized action log"}
  - {id: 8, title: "Generative Regis from day one", rule_summary: "PERSONA.md is the system prompt, not scripted variants"}
  - {id: 9, title: "Continuous build, not phased", rule_summary: "v1 prototype IS the v3 substrate"}
  - {id: 10, title: "Input classified by intent AND modality", rule_summary: "Two orthogonal axes at the L1 boundary"}
  - {id: 11, title: "Semantic-first continuous sensing", rule_summary: "Extract meaning, discard raw, cloud = escalation only"}
  - {id: 12, title: "Native clients talk to FastAPI", rule_summary: "The bridge is the seam"}
  - {id: 13, title: "Outcome-driven action selection", rule_summary: "Learned from observed outcomes (Thompson bandit v1)"}
  - {id: 14, title: "Meta-context biases every layer", rule_summary: "Waking/Sleep condition every layer's interpretation"}
  - {id: 15, title: "Regis as modeled controlled variable", rule_summary: "Counterfactual reasoning via predict(action)"}
  - {id: 16, title: "Prediction operates in latent space", rule_summary: "JEPA-family world model (LeWM recipe)"}
```

- [ ] **Step 3: Seed `docs/state/capabilities.yaml`**

Each entry's `evidence.modules` and `evidence.markers` were confirmed true in the 2026-06-01 audit (these modules import clean DB-free; these markers exist at these paths). `expected_test_count` is the audited DB-free full-tree count and will be updated in Task 5 once `state_ledger` tests are added.

```yaml
expected_test_count: 569

capabilities:
  - id: l1_l6_arc
    name: "L1->L6 reflex arc (assemble_pipeline)"
    serves_pillars: [multimodal_fusion, continuous_build]
    serves_commitments: [10, 14]
    build_state: built_and_runs
    alignment: on_track
    percent_done: 30
    gaps:
      - "Runs in one Mac process on synthetic data; never fed a real sensor packet"
    evidence:
      modules: ["core.pipeline"]
      markers: []
      key_files: ["core/pipeline.py"]

  - id: cognitive_load_axis
    name: "L3 cognitive_load fusion axis (BCI-derived)"
    serves_pillars: [multimodal_fusion]
    serves_commitments: [11, 14]
    build_state: scaffold
    alignment: partial
    percent_done: 25
    gaps:
      - "Heuristic, not trained; _ENGAGE_LO/_HI documented-not-fitted; EXG Pill uncalibrated"
    evidence:
      modules: ["fusion.participant"]
      markers:
        - {pattern: '"scaffold": True', path: "fusion/axes/cognitive_load.py", present: true}
      key_files: ["fusion/axes/cognitive_load.py"]

  - id: state_declared_axis
    name: "L3 state_declared axis (explicit self-report)"
    serves_pillars: [multimodal_fusion, provenance_labels]
    serves_commitments: [10]
    build_state: built_and_runs
    alignment: on_track
    percent_done: 60
    gaps:
      - "Quick-pick fallback is a coarse lexicon; LLM path is the real one"
    evidence:
      modules: ["fusion.participant"]
      markers:
        - {pattern: '"scaffold": False', path: "fusion/axes/state_declared.py", present: true}
      key_files: ["fusion/axes/state_declared.py"]

  - id: network_transport
    name: "NetworkTransport (Pi<->Mac relay)"
    serves_pillars: [distributed_topology]
    serves_commitments: [9]
    build_state: scaffold
    alignment: drifting
    percent_done: 35
    gaps:
      - "Passes unit tests but orphaned: every runtime builds an in-process bus; Pi daemon is dead"
    evidence:
      modules: ["core.bus.network"]
      markers: []
      key_files: ["core/bus/network.py"]

  - id: label_ledger
    name: "Provenance label ledger (#17)"
    serves_pillars: [provenance_labels]
    serves_commitments: [1]
    build_state: built_and_runs
    alignment: on_track
    percent_done: 70
    gaps:
      - "Cold-start calibration wired only into the declaration arc, not the default waking arc"
    evidence:
      modules: ["labels.ledger"]
      markers: []
      key_files: ["labels/ledger.py"]
```

- [ ] **Step 4: Seed `docs/state/workstreams.yaml`**

```yaml
workstreams:
  - id: doc-drift-fix
    title: "Fix STATUS.md / CLAUDE.md drift (601->569, remove stale v3 claims)"
    status: done
    owns_paths: ["docs/STATUS.md", "CLAUDE.md"]
    touches_commitments: []
    branch: null
    worktree: null
    github_issue: null
  - id: state-ledger-core
    title: "Build the State Ledger anti-drift core (this plan)"
    status: in_progress
    owns_paths: ["apps/inference/state_ledger/", "docs/state/"]
    touches_commitments: []
    branch: null
    worktree: null
    github_issue: null
  - id: first-real-signal
    title: "One real packet through the live arc (mic-first)"
    status: planned
    owns_paths: ["apps/inference/runtime/waking_arc.py", "apps/inference/voice/"]
    touches_commitments: [3, 11, 14]
    branch: null
    worktree: null
    github_issue: null
```

- [ ] **Step 5: Verify the YAML parses**

Run: `cd apps/inference && source .venv/bin/activate && python -c "import yaml,pathlib; [yaml.safe_load(open(p)) for p in pathlib.Path('../../docs/state').glob('*.yaml')]; print('yaml OK')"`
Expected: `yaml OK`

- [ ] **Step 6: Commit**

```bash
git add apps/inference/state_ledger/__init__.py docs/state/*.yaml
git commit -m "feat(state-ledger): seed manifest (pillars, capabilities, workstreams)"
```

---

## Task 2: Manifest schema + loader

**Files:**
- Create: `apps/inference/state_ledger/manifest.py`
- Test: `apps/inference/state_ledger/test_manifest.py`

- [ ] **Step 1: Write the failing test**

Create `apps/inference/state_ledger/test_manifest.py`:

```python
from __future__ import annotations

import pytest

from state_ledger.manifest import (Alignment, BuildState, Manifest,
                                    load_manifest)


def test_loads_real_manifest():
    m = load_manifest()
    assert isinstance(m, Manifest)
    assert len(m.commitments) == 16
    assert any(p.id == "multimodal_fusion" for p in m.pillars)
    assert m.expected_test_count > 0
    caps = {c.id: c for c in m.capabilities}
    assert caps["l1_l6_arc"].build_state is BuildState.BUILT_AND_RUNS
    assert caps["network_transport"].alignment is Alignment.DRIFTING


def test_rejects_bad_build_state(tmp_path):
    (tmp_path / "pillars.yaml").write_text("vision_pillars: []\ncommitments: []\n")
    (tmp_path / "workstreams.yaml").write_text("workstreams: []\n")
    (tmp_path / "capabilities.yaml").write_text(
        "expected_test_count: 1\n"
        "capabilities:\n"
        "  - {id: x, name: X, serves_pillars: [], serves_commitments: [],\n"
        "     build_state: NONSENSE, alignment: partial, percent_done: 0, gaps: []}\n"
    )
    with pytest.raises(ValueError):
        load_manifest(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/inference && source .venv/bin/activate && env -u DATABASE_URL python -m pytest state_ledger/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'state_ledger.manifest'`

- [ ] **Step 3: Write the implementation**

Create `apps/inference/state_ledger/manifest.py`:

```python
"""Manifest schema + loader — the State Ledger's single source of truth."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml

STATE_DIR = Path(__file__).resolve().parents[3] / "docs" / "state"


class BuildState(str, Enum):
    BUILT_AND_RUNS = "built_and_runs"
    SCAFFOLD = "scaffold"
    CODE_ONLY_UNVERIFIED = "code_only_unverified"
    ABSENT = "absent"


class Alignment(str, Enum):
    ON_TRACK = "on_track"
    PARTIAL = "partial"
    DRIFTING = "drifting"
    NOT_STARTED = "not_started"


class WorkstreamStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


@dataclass(frozen=True)
class Pillar:
    id: str
    name: str
    description: str
    centrality: str


@dataclass(frozen=True)
class Commitment:
    id: int
    title: str
    rule_summary: str


@dataclass(frozen=True)
class Marker:
    pattern: str
    path: str           # relative to apps/inference
    present: bool = True


@dataclass(frozen=True)
class Evidence:
    tests: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    key_files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    serves_pillars: list[str]
    serves_commitments: list[int]
    build_state: BuildState
    alignment: Alignment
    percent_done: int
    gaps: list[str]
    evidence: Evidence


@dataclass(frozen=True)
class Workstream:
    id: str
    title: str
    status: WorkstreamStatus
    owns_paths: list[str]
    touches_commitments: list[int]
    branch: str | None
    worktree: str | None
    github_issue: str | None


@dataclass(frozen=True)
class Manifest:
    pillars: list[Pillar]
    commitments: list[Commitment]
    capabilities: list[Capability]
    workstreams: list[Workstream]
    expected_test_count: int


def _load_yaml(path: Path):
    with path.open() as f:
        return yaml.safe_load(f)


def _parse_capability(d: dict) -> Capability:
    ev = d.get("evidence") or {}
    markers = [Marker(**m) for m in ev.get("markers", [])]
    evidence = Evidence(
        tests=list(ev.get("tests", [])),
        modules=list(ev.get("modules", [])),
        markers=markers,
        key_files=list(ev.get("key_files", [])),
    )
    return Capability(
        id=d["id"],
        name=d["name"],
        serves_pillars=list(d.get("serves_pillars", [])),
        serves_commitments=list(d.get("serves_commitments", [])),
        build_state=BuildState(d["build_state"]),
        alignment=Alignment(d["alignment"]),
        percent_done=int(d["percent_done"]),
        gaps=list(d.get("gaps", [])),
        evidence=evidence,
    )


def _parse_workstream(d: dict) -> Workstream:
    return Workstream(
        id=d["id"],
        title=d["title"],
        status=WorkstreamStatus(d["status"]),
        owns_paths=list(d.get("owns_paths", [])),
        touches_commitments=list(d.get("touches_commitments", [])),
        branch=d.get("branch"),
        worktree=d.get("worktree"),
        github_issue=d.get("github_issue"),
    )


def load_manifest(state_dir: Path = STATE_DIR) -> Manifest:
    pillars_doc = _load_yaml(state_dir / "pillars.yaml")
    caps_doc = _load_yaml(state_dir / "capabilities.yaml")
    ws_doc = _load_yaml(state_dir / "workstreams.yaml")
    return Manifest(
        pillars=[Pillar(**p) for p in pillars_doc.get("vision_pillars", [])],
        commitments=[Commitment(**c) for c in pillars_doc.get("commitments", [])],
        capabilities=[_parse_capability(c) for c in caps_doc.get("capabilities", [])],
        workstreams=[_parse_workstream(w) for w in ws_doc.get("workstreams", [])],
        expected_test_count=int(caps_doc["expected_test_count"]),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/inference && source .venv/bin/activate && env -u DATABASE_URL python -m pytest state_ledger/test_manifest.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/inference/state_ledger/manifest.py apps/inference/state_ledger/test_manifest.py
git commit -m "feat(state-ledger): typed manifest schema + YAML loader"
```

---

## Task 3: Mechanical verifier

**Files:**
- Create: `apps/inference/state_ledger/verify.py`
- Test: `apps/inference/state_ledger/test_verify.py`

The verifier checks only mechanical facts (imports, markers, workstream collisions, test count). Judgment fields (alignment, percent_done, gaps) are never checked here — they belong to the AI auditor (follow-on plan). Functions take inputs so they unit-test without running the real suite.

- [ ] **Step 1: Write the failing test**

Create `apps/inference/state_ledger/test_verify.py`:

```python
from __future__ import annotations

from state_ledger.manifest import (BuildState, Capability, Evidence, Marker,
                                    Workstream, WorkstreamStatus)
from state_ledger.manifest import Alignment
from state_ledger import verify


def _cap(**kw) -> Capability:
    base = dict(
        id="c", name="C", serves_pillars=[], serves_commitments=[],
        build_state=BuildState.BUILT_AND_RUNS, alignment=Alignment.ON_TRACK,
        percent_done=0, gaps=[], evidence=Evidence(),
    )
    base.update(kw)
    return Capability(**base)


def test_import_violation_when_module_missing():
    cap = _cap(evidence=Evidence(modules=["state_ledger._definitely_not_real"]))
    out = verify.check_imports(cap)
    assert len(out) == 1
    assert "failed to import" in out[0]


def test_import_ok_for_real_module():
    cap = _cap(evidence=Evidence(modules=["state_ledger.manifest"]))
    assert verify.check_imports(cap) == []


def test_absent_capability_skips_imports():
    cap = _cap(build_state=BuildState.ABSENT,
               evidence=Evidence(modules=["state_ledger._definitely_not_real"]))
    assert verify.check_imports(cap) == []


def test_marker_present_check(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text('x = {"scaffold": True}\n')
    ok = _cap(evidence=Evidence(markers=[Marker(pattern='"scaffold": True',
                                                 path="sample.py", present=True)]))
    bad = _cap(evidence=Evidence(markers=[Marker(pattern='"scaffold": False',
                                                 path="sample.py", present=True)]))
    assert verify.check_markers(ok, root=tmp_path) == []
    assert len(verify.check_markers(bad, root=tmp_path)) == 1


def test_workstream_collision():
    a = Workstream(id="a", title="A", status=WorkstreamStatus.IN_PROGRESS,
                   owns_paths=["shared/x.py"], touches_commitments=[],
                   branch=None, worktree=None, github_issue=None)
    b = Workstream(id="b", title="B", status=WorkstreamStatus.IN_PROGRESS,
                   owns_paths=["shared/x.py"], touches_commitments=[],
                   branch=None, worktree=None, github_issue=None)
    out = verify.check_workstream_collisions([a, b])
    assert len(out) == 1 and "collision" in out[0]


def test_test_count_drift():
    assert verify.check_test_count(569, 569) == []
    out = verify.check_test_count(569, 575)
    assert len(out) == 1 and "575" in out[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/inference && source .venv/bin/activate && env -u DATABASE_URL python -m pytest state_ledger/test_verify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'state_ledger.verify'`

- [ ] **Step 3: Write the implementation**

Create `apps/inference/state_ledger/verify.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/inference && source .venv/bin/activate && env -u DATABASE_URL python -m pytest state_ledger/test_verify.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Run the verifier against the real manifest**

Run: `cd apps/inference && source .venv/bin/activate && env -u DATABASE_URL python -m state_ledger.verify`
Expected: prints `STATE LEDGER VERIFY: FAIL` with exactly one violation — the test-count drift (collected count is now > 569 because `state_ledger` tests were added). This proves the count check works; it is fixed in Task 5.

- [ ] **Step 6: Commit**

```bash
git add apps/inference/state_ledger/verify.py apps/inference/state_ledger/test_verify.py
git commit -m "feat(state-ledger): mechanical verifier (imports, markers, collisions, test-count)"
```

---

## Task 4: Renderer (STATUS block + state.json)

**Files:**
- Create: `apps/inference/state_ledger/render.py`
- Test: `apps/inference/state_ledger/test_render.py`
- Modify: `docs/STATUS.md` (insert the STATE markers once)

- [ ] **Step 1: Write the failing test**

Create `apps/inference/state_ledger/test_render.py`:

```python
from __future__ import annotations

import json

from state_ledger import render
from state_ledger.manifest import load_manifest


def test_status_block_has_markers_and_caps():
    m = load_manifest()
    block = render.render_status_block(m)
    assert render.BEGIN in block and render.END in block
    assert "L1->L6 reflex arc" in block


def test_splice_is_idempotent():
    m = load_manifest()
    block = render.render_status_block(m)
    doc = f"# Title\n\nintro\n\n{render.BEGIN}\nOLD\n{render.END}\n\ntail\n"
    once = render.splice_status(doc, block)
    twice = render.splice_status(once, block)
    assert once == twice
    assert "OLD" not in once
    assert "tail" in once and "intro" in once


def test_splice_inserts_when_no_markers():
    m = load_manifest()
    block = render.render_status_block(m)
    out = render.splice_status("# Title\n\nbody\n", block)
    assert render.BEGIN in out and "body" in out


def test_state_json_shape():
    m = load_manifest()
    data = render.render_state_json(m)
    assert json.loads(json.dumps(data))  # serializable
    assert {"pillars", "commitments", "capabilities", "workstreams",
            "expected_test_count"} <= set(data)
    cap = next(c for c in data["capabilities"] if c["id"] == "network_transport")
    assert cap["build_state"] == "scaffold"
    assert cap["alignment"] == "drifting"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/inference && source .venv/bin/activate && env -u DATABASE_URL python -m pytest state_ledger/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'state_ledger.render'`

- [ ] **Step 3: Write the implementation**

Create `apps/inference/state_ledger/render.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/inference && source .venv/bin/activate && env -u DATABASE_URL python -m pytest state_ledger/test_render.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Insert the STATE markers into STATUS.md**

The generated block goes directly under the H1 title. Manually add the two marker lines once so future renders splice between them. Edit `docs/STATUS.md`: immediately after the first line (`# Daybook — Big Picture Status`), insert a blank line then:

```markdown
<!-- STATE:BEGIN -->
<!-- STATE:END -->
```

- [ ] **Step 6: Run the renderer and eyeball STATUS.md**

Run: `cd apps/inference && source .venv/bin/activate && env -u DATABASE_URL python -m state_ledger.render`
Expected: `rendered: STATUS.md block + state.json`. Open `docs/STATUS.md` — the generated capability table sits between the markers; the dated history below is untouched. `docs/state/state.json` now exists.

- [ ] **Step 7: Verify render idempotency on the real file**

Run: `cd apps/inference && source .venv/bin/activate && env -u DATABASE_URL python -m state_ledger.render && git diff --stat docs/STATUS.md`
Then run render once more.
Expected: the second render produces no further change to `docs/STATUS.md` (byte-identical between the markers).

- [ ] **Step 8: Commit**

```bash
git add apps/inference/state_ledger/render.py apps/inference/state_ledger/test_render.py docs/STATUS.md docs/state/state.json
git commit -m "feat(state-ledger): renderer for STATUS block + state.json; wire STATUS markers"
```

---

## Task 5: Fix the test count + CI gate

**Files:**
- Modify: `docs/state/capabilities.yaml` (set true `expected_test_count`)
- Create: `.github/workflows/state-verify.yml`

- [ ] **Step 1: Measure the real collected count**

Run: `cd apps/inference && source .venv/bin/activate && env -u DATABASE_URL python -c "from state_ledger import verify; print(verify.collect_test_count())"`
Expected: a number > 569 (569 audited + the ~13 new `state_ledger` tests). Note the exact value, call it `N`.

- [ ] **Step 2: Update the manifest**

Edit `docs/state/capabilities.yaml`: change `expected_test_count: 569` to `expected_test_count: N` (the value from Step 1).

- [ ] **Step 3: Verify the full verifier now passes**

Run: `cd apps/inference && source .venv/bin/activate && env -u DATABASE_URL python -m state_ledger.verify`
Expected: `STATE LEDGER VERIFY: OK` (exit 0).

- [ ] **Step 4: Create the CI workflow**

Create `.github/workflows/state-verify.yml`:

```yaml
name: state-verify
on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/inference
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install deps
        run: pip install -e . && pip install pyyaml pytest
      - name: State Ledger verify (manifest can't lie)
        env:
          DATABASE_URL: ""
        run: python -m state_ledger.verify
      - name: Render-staleness check (generated outputs match manifest)
        env:
          DATABASE_URL: ""
        run: |
          python -m state_ledger.render
          git diff --exit-code docs/STATUS.md docs/state/state.json \
            || (echo "STATUS.md / state.json are stale vs the manifest — run 'python -m state_ledger.render' and commit." && exit 1)
```

Note: `pip install -e .` installs the inference package per its `pyproject.toml`. If the package install does not expose the layer modules as importable top-level names in CI the way the local `.venv` does, the import checks will surface it here — that is the correct place to catch it, and the fix is to align CI's install with the local editable install. Confirm CI passes before merging.

- [ ] **Step 5: Commit**

```bash
git add docs/state/capabilities.yaml .github/workflows/state-verify.yml
git commit -m "feat(state-ledger): pin test count + per-PR CI verify & render-staleness gate"
```

---

## Task 6: Ledger README + final integration check

**Files:**
- Create: `docs/state/README.md`

- [ ] **Step 1: Write the README**

Create `docs/state/README.md`:

```markdown
# Daybook State Ledger

This directory is the **single source of truth** for project state. Edit the
manifest here; everything else (the STATUS.md "Current state" block, `state.json`,
the dashboard, GitHub issues) is **generated** — never edit generated outputs by hand.

## Files
- `pillars.yaml` — vision pillars + the 16 architectural commitments.
- `capabilities.yaml` — `expected_test_count` + every real capability with
  build_state / alignment / percent_done / gaps / evidence.
- `workstreams.yaml` — active/planned parallel efforts (with `owns_paths`).
- `state.json` — generated dashboard feed (do not edit).

## Commands (from `apps/inference`, venv active, DATABASE_URL unset)
- `python -m state_ledger.verify` — fails if the manifest's mechanical claims
  (module imports, code markers, test count, workstream collisions) don't match the repo.
- `python -m state_ledger.render` — regenerates the STATUS.md block + `state.json`.

## How drift is prevented
- The **verifier** runs in CI per-PR: a false mechanical claim fails the build.
- The **render-staleness check** fails CI if generated outputs don't match the manifest.
- Judgment fields (alignment / percent_done / gaps) are re-derived by the periodic
  AI **auditor** (separate plan), which proposes manifest updates via PR.

## Adding a capability
Add an entry to `capabilities.yaml` with real `evidence` (modules that import,
markers that exist). Run `verify` then `render`, and commit both.
```

- [ ] **Step 2: Full integration run**

Run:
```bash
cd apps/inference && source .venv/bin/activate
env -u DATABASE_URL python -m pytest state_ledger -v
env -u DATABASE_URL python -m state_ledger.verify
env -u DATABASE_URL python -m state_ledger.render
git diff --exit-code docs/STATUS.md docs/state/state.json
```
Expected: state_ledger tests all pass; verify prints `OK` (exit 0); render runs; `git diff --exit-code` shows no diff (already rendered → outputs are current).

- [ ] **Step 3: Confirm the full suite is still green**

Run: `cd apps/inference && source .venv/bin/activate && env -u DATABASE_URL python -m pytest -q | tail -3`
Expected: `N passed` where N matches `expected_test_count` in `capabilities.yaml`.

- [ ] **Step 4: Commit**

```bash
git add docs/state/README.md
git commit -m "docs(state-ledger): README — edit the manifest, never the generated outputs"
```

---

## Self-Review notes

- **Spec coverage:** This plan covers spec §4.1 (manifest), §4.2 (verifier), §4.4 (renderer: STATUS block + state.json), §7 (file layout, adapted to `apps/inference/state_ledger/`), §8 (testing), and §6 (seed content). **Deferred to follow-on plans (by design, see spec §4.3, §4.5, §4.6):** the AI auditor workflow, the dashboard UI + Cloudflare Pages/Access hosting, and GitHub Issues/Project sync. The render-staleness CI check here is the hook those will extend.
- **Test-count check:** intentionally exact (not a floor) so adding/removing tests forces a deliberate `expected_test_count` bump — the same discipline that would have caught 601-vs-569.
- **Path assumption:** layer modules (`core.pipeline`, `fusion.participant`, etc.) are importable when CWD is `apps/inference` with the venv active — confirmed by the 2026-06-01 audit. Task 5 Step 4 flags CI install alignment as the one thing to confirm on first CI run.
