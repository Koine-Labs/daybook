from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio_context import ambient


def test_classify_returns_empty_when_unavailable(monkeypatch):
    monkeypatch.setattr(ambient, "_model", lambda: None)
    out = ambient.classify_ambient(np.zeros(16000, dtype=np.float32), 16000, top_k=3)
    assert out == []


def test_classify_shapes_topk(monkeypatch):
    class _FakeModel:
        def __call__(self, waveform):
            import numpy as _np
            # 2 frames x 3 classes (cols: Silence, Speech, Music).
            # mean(axis=0) = [0.1, 0.65, 0.25] -> Speech > Music > Silence.
            scores = _np.array([[0.1, 0.7, 0.2], [0.1, 0.6, 0.3]], dtype=_np.float32)
            return scores, None, None
    monkeypatch.setattr(ambient, "_model", lambda: _FakeModel())
    monkeypatch.setattr(ambient, "_class_names", lambda: ["Silence", "Speech", "Music"])
    out = ambient.classify_ambient(np.ones(16000, dtype=np.float32), 16000, top_k=2)
    assert [c["class"] for c in out] == ["Speech", "Music"]
    assert out[0]["score"] >= out[1]["score"]
