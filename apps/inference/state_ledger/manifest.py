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
