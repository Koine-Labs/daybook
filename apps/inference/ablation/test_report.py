"""report — honest manifest + markdown lists tested/dropped/capped with reasons."""
from __future__ import annotations

import sys
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from ablation.report import build_manifest, render_markdown
from ablation.store import AblationResultRow


def _res(source_set, brier=None, dropped=None):
    return AblationResultRow(
        run_id="r1", user_id="u1", axis="arousal_inferred", meta_context=None,
        source_set=tuple(source_set),
        metrics=({"brier": brier} if brier is not None else {}),
        n_train_pairs=10, n_eval_pairs=(10 if brier is not None else 0),
        grader="self_report", label_sources=["self_report"],
        beat_components=None, dropped_reason=dropped,
    )


def test_manifest_lists_tested_and_dropped() -> None:
    results = {
        "arousal_inferred": [
            _res(("eeg",), brier=0.2),
            _res(("eeg", "eog", "mic"), dropped="capped_by_max_set_size"),
            _res(("eog",), dropped="insufficient_data"),
        ]
    }
    manifest = build_manifest(results, promoted={"arousal_inferred": [("eeg", "eog")]})
    axis = manifest["axes"]["arousal_inferred"]
    assert axis["tested"] == 1
    assert axis["dropped"]["capped_by_max_set_size"] == 1
    assert axis["dropped"]["insufficient_data"] == 1
    assert ["eeg", "eog"] in [list(s) for s in axis["promoted"]]


def test_manifest_records_dropped_sets_explicitly() -> None:
    results = {"a": [_res(("x", "y", "z"), dropped="capped_by_max_set_size")]}
    manifest = build_manifest(results, promoted={})
    dropped_detail = manifest["axes"]["a"]["dropped_sets"]
    assert any(
        list(d["source_set"]) == ["x", "y", "z"]
        and d["reason"] == "capped_by_max_set_size"
        for d in dropped_detail
    )


def test_markdown_has_dropped_section() -> None:
    results = {
        "a": [
            _res(("eeg",), brier=0.2),
            _res(("eeg", "eog", "mic"), dropped="capped_by_max_set_size"),
        ]
    }
    md = render_markdown(results, promoted={})
    assert "Dropped" in md
    assert "capped_by_max_set_size" in md
    assert "eeg" in md
