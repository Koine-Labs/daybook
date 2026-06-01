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
