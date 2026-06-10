from __future__ import annotations

import json

from state_ledger import render
from state_ledger.manifest import Alignment, BuildState, load_manifest


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
    assert cap["build_state"] in {s.value for s in BuildState}
    assert cap["alignment"] in {a.value for a in Alignment}
