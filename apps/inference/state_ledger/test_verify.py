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
