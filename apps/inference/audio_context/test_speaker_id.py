from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio_context import speaker_id


def test_identify_self_vs_other():
    centroid = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    near = np.array([0.99, 0.01, 0.0], dtype=np.float32)     # cosine ~1.0
    far = np.array([0.0, 1.0, 0.0], dtype=np.float32)        # cosine 0
    assert speaker_id.identify(near, centroid=centroid, threshold=0.75) == "self"
    assert speaker_id.identify(far, centroid=centroid, threshold=0.75) == "other"


def test_identify_no_centroid_is_unknown():
    emb = np.array([1.0, 0.0], dtype=np.float32)
    assert speaker_id.identify(emb, centroid=None) == "unknown"


def test_cosine():
    a = np.array([1.0, 0.0]); b = np.array([1.0, 0.0])
    assert abs(speaker_id._cosine(a, b) - 1.0) < 1e-6
    c = np.array([0.0, 1.0])
    assert abs(speaker_id._cosine(a, c)) < 1e-6
