# Week 3 — Continuous Mic Semantic Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make Daybook *continuously* aware of the audio environment — VAD → speaker identity → prosody → ambient — on ONE always-on mic loop, gated by Privacy Policy #1 (non-Aakash voice pauses everything but a presence marker). Lights the `audio_social_context` axis and lightly refines `arousal_inferred`.

**Architecture:** Re-pull the salvageable `audio_context/` primitives (VAD/diarization/prosody/processor) from `v0-pre-rebuild`. Add speaker *identity* (enroll Aakash, classify each utterance), a differentiated packet taxonomy written to `sensor_readings` with `consent_scope`, a unit-tested Privacy Policy #1 state machine, a lazy YAMNet ambient backend, and the `audio_social_context` L3 axis. Fold continuous listening into `apps/voice/loop.py`'s single mic loop — the same stream that already does wake-word detection (no two-process mic contention).

**Tech Stack:** silero-vad (Silero VAD), resemblyzer (speaker embedding), librosa (prosody/resample), scikit-learn (clustering — already present), torch (already present), tensorflow-hub + tensorflow (YAMNet — isolated lazy backend), Neon `sensor_readings`.

**Conventions (CLAUDE.md):** run from `apps/` with `apps/inference/.venv` active; `from db import get_conn` after the `sys.path` bootstrap; tz-aware UTC; `DEFAULT_USER_ID="61c18d4c-1c20-408a-bd5f-f5f88fd9922f"`; `from __future__ import annotations`; one-line docstrings.

**Privacy is load-bearing.** Task 5 (the gate) is the security keystone — it must be a pure, unit-tested component the loop calls, not logic scattered through the loop. Default to suppression on any uncertainty.

**Pre-flight:**
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git checkout main && git pull
git checkout -b feat/week-3-continuous-mic
source apps/inference/.venv/bin/activate
```

---

## Task 1: Re-pull `audio_context/` primitives + deps

**Files:**
- Restore from tag: `apps/inference/audio_context/{__init__,vad,diarization,prosody,processor,persistor,smoke_test}.py`
- Modify: `apps/inference/pyproject.toml`

- [ ] **Step 1: Restore the package from the tag**
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git checkout v0-pre-rebuild -- apps/inference/audio_context/
ls apps/inference/audio_context/
```
Expected: `__init__.py diarization.py persistor.py processor.py prosody.py smoke_test.py vad.py`.

- [ ] **Step 2: Add deps** to `apps/inference/pyproject.toml` `dependencies` (after the openwakeword/onnxruntime block):
```toml
    # Continuous mic semantic pipeline (Week 3). silero-vad (VAD), resemblyzer
    # (speaker embedding), librosa (prosody/resample). torch + scikit-learn already present.
    "silero-vad>=5.1",
    "resemblyzer>=0.1.3",
    "librosa>=0.10.0",
```

- [ ] **Step 3: Install**
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
source .venv/bin/activate
uv pip install "silero-vad>=5.1" "resemblyzer>=0.1.3" "librosa>=0.10.0"
```
Expected: installs (pulls torch deps if missing — torch is already present via sentence-transformers).

- [ ] **Step 4: Verify imports + a synthetic VAD/prosody round-trip (no mic)**
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
python - <<'PY'
import numpy as np
from audio_context.vad import detect_voice_activity
from audio_context.prosody import extract_prosody
sr=16000
silence=np.zeros(sr, dtype=np.float32)
print("vad(silence):", detect_voice_activity(silence, sr))
p=extract_prosody(silence, sr); print("prosody(silence):", p.to_dict())
PY
```
Expected: `vad(silence): []` and a ProsodyFeatures dict (energy ~0, tone a string). No import errors.

- [ ] **Step 5: Run the package smoke** (it may require a mic; if it does and none exists, note it must run on the dev Mac):
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
python -m audio_context.smoke_test 2>&1 | tail -20 || echo "smoke needs review (mic / DB) — note exact failure"
```
If the smoke depends on a flat `audio_segment` persist that Task 4 will replace, note it; the synthetic round-trip in Step 4 is the definitive Task-1 check.

- [ ] **Step 6: Commit**
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/inference/audio_context/ apps/inference/pyproject.toml
git commit -m "feat(audio): re-pull audio_context primitives (vad/diarization/prosody) + deps"
```

---

## Task 2: Activate the `voice` consent scope

**Files:**
- Modify: `apps/inference/consent.py`
- Test: `apps/inference/test_consent.py`

- [ ] **Step 1: Write the failing test** `apps/inference/test_consent.py`:
```python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from consent import CONSENT_SCOPES


def test_voice_scope_active():
    assert CONSENT_SCOPES["voice"] == "mic_continuous_v1"
    # existing scopes intact
    assert CONSENT_SCOPES["mac"] == "mac_activity_v1"
    assert CONSENT_SCOPES["hk"] == "apple_health_v1"
```

- [ ] **Step 2: Run it; confirm FAIL** (`KeyError: 'voice'`).

- [ ] **Step 3: Edit `consent.py`** — uncomment/activate the voice scope:
```python
CONSENT_SCOPES: dict[str, str] = {
    "mac": "mac_activity_v1",
    "hk": "apple_health_v1",
    "voice": "mic_continuous_v1",  # Week 3 continuous-mic opt-in
    # "eeg": "eeg_continuous_v1",   # reserved — BioAmp EXG Pill onboarding
}
```

- [ ] **Step 4: Run it; confirm 1 passed.**

- [ ] **Step 5: Commit**
```bash
git add apps/inference/consent.py apps/inference/test_consent.py
git commit -m "feat(consent): activate voice scope mic_continuous_v1 (Week 3)"
```

---

## Task 3: Speaker identity — `speaker_id.py` (enroll + identify)

**Files:**
- Create: `apps/inference/audio_context/speaker_id.py`
- Test: `apps/inference/audio_context/test_speaker_id.py`

**Context:** `diarization.py` already lazily builds a resemblyzer `VoiceEncoder` via `_encoder()` and embeds windows. We add *identity*: enroll the user's centroid from reference clips, classify a new embedding by cosine similarity. Centroid persists to `~/.daybook/speaker_<user_id>.npy`. Returns `"self"` (== the enrolled user, i.e. Aakash) or `"other"`.

- [ ] **Step 1: Write the failing test** `apps/inference/audio_context/test_speaker_id.py`:
```python
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
```

- [ ] **Step 2: Run it; confirm FAIL** (no module `speaker_id`).

- [ ] **Step 3: Create `apps/inference/audio_context/speaker_id.py`:**
```python
"""Speaker identity: enroll the user's voice centroid, classify utterances."""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_THRESHOLD = 0.75
ENROLL_DIR = Path.home() / ".daybook"


@lru_cache(maxsize=1)
def _encoder():
    from resemblyzer import VoiceEncoder
    return VoiceEncoder()


def _centroid_path(user_id: str) -> Path:
    return ENROLL_DIR / f"speaker_{user_id}.npy"


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def embed_utterance(audio: np.ndarray, sample_rate: int) -> np.ndarray | None:
    """resemblyzer embedding for one utterance; None if too short."""
    from resemblyzer import preprocess_wav
    samples = np.asarray(audio, dtype=np.float32)
    if samples.size == 0:
        return None
    try:
        wav = preprocess_wav(samples, source_sr=sample_rate)
        return _encoder().embed_utterance(wav)
    except Exception:
        return None


def enroll(user_id: str, wav_paths: list[Path]) -> np.ndarray:
    """Embed each reference clip, store the mean centroid. Returns the centroid."""
    import soundfile as sf
    embeddings: list[np.ndarray] = []
    for p in wav_paths:
        audio, sr = sf.read(str(p), dtype="float32")
        if audio.ndim == 2:
            audio = audio.mean(axis=1)
        emb = embed_utterance(audio, sr)
        if emb is not None:
            embeddings.append(emb)
    if not embeddings:
        raise ValueError("no usable reference clips for enrollment")
    centroid = np.mean(np.stack(embeddings), axis=0).astype(np.float32)
    ENROLL_DIR.mkdir(parents=True, exist_ok=True)
    np.save(_centroid_path(user_id), centroid)
    return centroid


def load_centroid(user_id: str) -> np.ndarray | None:
    p = _centroid_path(user_id)
    return np.load(p) if p.exists() else None


def identify(
    embedding: np.ndarray,
    *,
    centroid: np.ndarray | None,
    threshold: float = DEFAULT_THRESHOLD,
) -> str:
    """'self' if cosine(embedding, centroid) >= threshold, 'other' if below,
    'unknown' if no centroid is enrolled."""
    if centroid is None:
        return "unknown"
    return "self" if _cosine(embedding, centroid) >= threshold else "other"
```

- [ ] **Step 4: Run it; confirm 3 passed.**

- [ ] **Step 5: Commit**
```bash
git add apps/inference/audio_context/speaker_id.py apps/inference/audio_context/test_speaker_id.py
git commit -m "feat(audio): speaker identity — enroll centroid + cosine identify (self/other)"
```

> **Manual enrollment** (after merge, like the Hey-Regis model): record 3–5 short clips of Aakash speaking, then `python -c "from audio_context.speaker_id import enroll; from pathlib import Path; enroll('61c18d4c-1c20-408a-bd5f-f5f88fd9922f', [Path('clip1.wav'), Path('clip2.wav')])"`. Until enrolled, `identify` returns `'unknown'` and the privacy gate (Task 5) treats unknown conservatively.

---

## Task 4: Packet taxonomy writer — `audio_context/writer.py`

**Files:**
- Create: `apps/inference/audio_context/writer.py`
- Test: `apps/inference/audio_context/test_writer.py`

**Context:** Replaces the tag's flat `persist_packet(kind='audio_segment')` with the three differentiated kinds, each stamped with `consent_scope`. Mirrors the `sensor_readings` write convention from `capture/mac_sensors.py` (`user_id, kind, recorded_at, source, payload, consent_scope`).

- [ ] **Step 1: Write the failing test** `apps/inference/audio_context/test_writer.py`:
```python
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio_context import writer


class _Cur:
    def __init__(self): self.calls = []
    def execute(self, sql, params): self.calls.append((sql, params))
    def fetchone(self): return ("row-id",)
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Conn:
    def __init__(self): self.cur_obj = _Cur(); self.committed = False
    def cursor(self): return self.cur_obj
    def commit(self): self.committed = True
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _patch(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(writer, "get_conn", lambda: conn)
    return conn


def test_write_social_context_stamps_consent(monkeypatch):
    conn = _patch(monkeypatch)
    now = datetime.now(timezone.utc)
    rid = writer.write_social_context("u1", now, speaker="other", num_speakers=2, vad_active=True)
    assert rid == "row-id"
    sql, params = conn.cur_obj.calls[0]
    assert "audio_social_context" in sql
    assert "mic_continuous_v1" in params  # consent_scope present
    assert conn.committed


def test_write_prosody_and_ambient(monkeypatch):
    conn = _patch(monkeypatch)
    now = datetime.now(timezone.utc)
    writer.write_prosody("u1", now, {"energy": 0.1, "tone": "calm"})
    writer.write_ambient("u1", now, [{"class": "Speech", "score": 0.8}])
    kinds = [c[0] for c in conn.cur_obj.calls]
    assert any("audio_prosody" in s for s in kinds)
    assert any("audio_ambient" in s for s in kinds)
```

- [ ] **Step 2: Run it; confirm FAIL** (no `writer`).

- [ ] **Step 3: Create `apps/inference/audio_context/writer.py`:**
```python
"""Differentiated audio semantic packet writers (Week 3 taxonomy)."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from consent import CONSENT_SCOPES  # noqa: E402
from db import get_conn  # noqa: E402

SOURCE = "mic_listener_v1"
_SCOPE = CONSENT_SCOPES["voice"]


def _insert(user_id: str, kind: str, recorded_at: datetime, payload: dict[str, Any]) -> str:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sensor_readings
                (user_id, kind, recorded_at, source, payload, consent_scope)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            RETURNING id
            """,
            (user_id, kind, recorded_at, SOURCE, json.dumps(payload), _SCOPE),
        )
        row = cur.fetchone()
        conn.commit()
    return str(row[0])


def write_social_context(user_id: str, recorded_at: datetime, *, speaker: str,
                         num_speakers: int, vad_active: bool) -> str:
    """speaker: 'self' | 'other' | 'both' | 'none'."""
    return _insert(user_id, "audio_social_context", recorded_at,
                   {"speaker": speaker, "num_speakers": num_speakers, "vad_active": vad_active})


def write_prosody(user_id: str, recorded_at: datetime, prosody: dict[str, Any]) -> str:
    return _insert(user_id, "audio_prosody", recorded_at, prosody)


def write_ambient(user_id: str, recorded_at: datetime, top_classes: list[dict[str, Any]]) -> str:
    return _insert(user_id, "audio_ambient", recorded_at, {"top_classes": top_classes})
```

- [ ] **Step 4: Run it; confirm 2 passed.**

- [ ] **Step 5: Commit**
```bash
git add apps/inference/audio_context/writer.py apps/inference/audio_context/test_writer.py
git commit -m "feat(audio): differentiated packet writers (social_context/prosody/ambient) + consent_scope"
```

---

## Task 5: Privacy Policy #1 state machine — `audio_context/privacy.py`

**Files:**
- Create: `apps/inference/audio_context/privacy.py`
- Test: `apps/inference/audio_context/test_privacy.py`

**Context (locked spec §5):** non-Aakash voice → write only a presence marker; suppress prosody + ambient + STT for that window **plus a 30s silence buffer**. The gate is a pure state machine: feed it the identified speakers of the current window + `now`; it returns what's allowed and updates its suppression deadline. Default to suppression under uncertainty (`unknown` speaker counts as other).

- [ ] **Step 1: Write the failing test** `apps/inference/audio_context/test_privacy.py`:
```python
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio_context.privacy import PrivacyGate


def test_self_only_allows_everything():
    g = PrivacyGate(buffer_seconds=30)
    now = datetime.now(timezone.utc)
    d = g.evaluate(speakers=["self"], now=now)
    assert d.social_context == "self"
    assert d.allow_prosody and d.allow_ambient and d.allow_stt


def test_other_voice_suppresses_and_marks_both():
    g = PrivacyGate(buffer_seconds=30)
    now = datetime.now(timezone.utc)
    d = g.evaluate(speakers=["self", "other"], now=now)
    assert d.social_context == "both"
    assert not d.allow_prosody and not d.allow_ambient and not d.allow_stt
    assert d.suppressed_until == now + timedelta(seconds=30)


def test_suppression_persists_through_buffer_after_other_leaves():
    g = PrivacyGate(buffer_seconds=30)
    t0 = datetime.now(timezone.utc)
    g.evaluate(speakers=["other"], now=t0)                       # triggers suppression
    d = g.evaluate(speakers=["self"], now=t0 + timedelta(seconds=10))  # within buffer
    assert not d.allow_prosody and not d.allow_ambient
    d2 = g.evaluate(speakers=["self"], now=t0 + timedelta(seconds=31)) # past buffer
    assert d2.allow_prosody and d2.allow_ambient


def test_unknown_speaker_treated_as_other():
    g = PrivacyGate(buffer_seconds=30)
    now = datetime.now(timezone.utc)
    d = g.evaluate(speakers=["unknown"], now=now)
    assert d.social_context == "other"
    assert not d.allow_prosody


def test_silence_allows_ambient_only():
    g = PrivacyGate(buffer_seconds=30)
    now = datetime.now(timezone.utc)
    d = g.evaluate(speakers=[], now=now)
    assert d.social_context == "none"
    assert d.allow_ambient and not d.allow_prosody  # prosody needs voiced self-speech
```

- [ ] **Step 2: Run it; confirm FAIL** (no `privacy`).

- [ ] **Step 3: Create `apps/inference/audio_context/privacy.py`:**
```python
"""Privacy Policy #1 — pause-on-other-voice. Pure, testable state machine."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

DEFAULT_BUFFER_SECONDS = 30.0


@dataclass
class GateDecision:
    social_context: str          # 'self' | 'other' | 'both' | 'none'
    allow_prosody: bool
    allow_ambient: bool
    allow_stt: bool
    suppressed_until: datetime | None


class PrivacyGate:
    """Tracks a suppression deadline. 'unknown' speakers count as 'other'."""

    def __init__(self, *, buffer_seconds: float = DEFAULT_BUFFER_SECONDS) -> None:
        self.buffer_seconds = buffer_seconds
        self._suppressed_until: datetime | None = None

    def _classify(self, speakers: list[str]) -> str:
        has_self = "self" in speakers
        has_other = any(s in ("other", "unknown") for s in speakers)
        if has_self and has_other:
            return "both"
        if has_other:
            return "other"
        if has_self:
            return "self"
        return "none"

    def evaluate(self, *, speakers: list[str], now: datetime) -> GateDecision:
        social = self._classify(speakers)

        if social in ("other", "both"):
            self._suppressed_until = now + timedelta(seconds=self.buffer_seconds)

        suppressed = self._suppressed_until is not None and now < self._suppressed_until

        # Prosody only on voiced self-speech that isn't suppressed.
        allow_prosody = (social == "self") and not suppressed
        # Ambient runs during non-suppressed silence/self windows.
        allow_ambient = (social in ("self", "none")) and not suppressed
        allow_stt = (social in ("self", "none")) and not suppressed

        return GateDecision(
            social_context=social,
            allow_prosody=allow_prosody,
            allow_ambient=allow_ambient,
            allow_stt=allow_stt,
            suppressed_until=self._suppressed_until,
        )
```

- [ ] **Step 4: Run it; confirm 5 passed.**

- [ ] **Step 5: Commit**
```bash
git add apps/inference/audio_context/privacy.py apps/inference/audio_context/test_privacy.py
git commit -m "feat(audio): Privacy Policy #1 gate — pause-on-other-voice + 30s buffer (tested)"
```

---

## Task 6: YAMNet ambient — `audio_context/ambient.py` (lazy backend)

**Files:**
- Create: `apps/inference/audio_context/ambient.py`
- Test: `apps/inference/audio_context/test_ambient.py`
- Modify: `apps/inference/pyproject.toml`

**Context:** YAMNet via tensorflow-hub is heavy and must NOT be able to break the core pipeline. Mirror the TTS `say/kokoro/none` pattern: lazy import, `is_available()` probe, and `classify_ambient` returns `[]` when unavailable. Add TF deps in an OPTIONAL group so the base install stays lean.

- [ ] **Step 1: Write the failing test** `apps/inference/audio_context/test_ambient.py`:
```python
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
            # 2 frames x 3 classes
            scores = _np.array([[0.1, 0.7, 0.2], [0.3, 0.6, 0.1]], dtype=_np.float32)
            return scores, None, None
    monkeypatch.setattr(ambient, "_model", lambda: _FakeModel())
    monkeypatch.setattr(ambient, "_class_names", lambda: ["Silence", "Speech", "Music"])
    out = ambient.classify_ambient(np.ones(16000, dtype=np.float32), 16000, top_k=2)
    assert [c["class"] for c in out] == ["Speech", "Music"]
    assert out[0]["score"] >= out[1]["score"]
```

- [ ] **Step 2: Run it; confirm FAIL** (no `ambient`).

- [ ] **Step 3: Create `apps/inference/audio_context/ambient.py`:**
```python
"""Ambient sound classification via YAMNet — lazy, optional, fail-soft."""
from __future__ import annotations

import csv
from functools import lru_cache

import numpy as np

_YAMNET_HANDLE = "https://tfhub.dev/google/yamnet/1"


@lru_cache(maxsize=1)
def _model():
    """Load YAMNet from tfhub; return None if tensorflow_hub isn't installed."""
    try:
        import tensorflow_hub as hub
        return hub.load(_YAMNET_HANDLE)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _class_names() -> list[str]:
    m = _model()
    if m is None:
        return []
    import tensorflow as tf
    path = m.class_map_path().numpy()
    names: list[str] = []
    with tf.io.gfile.GFile(path) as f:
        for row in csv.DictReader(f):
            names.append(row["display_name"])
    return names


def is_available() -> bool:
    return _model() is not None


def classify_ambient(audio: np.ndarray, sample_rate: int, *, top_k: int = 3) -> list[dict]:
    """Return [{class, score}] for the dominant ambient classes, or [] if unavailable.

    YAMNet expects 16 kHz mono float32 in [-1, 1].
    """
    model = _model()
    if model is None:
        return []
    samples = np.asarray(audio, dtype=np.float32)
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    if sample_rate != 16000:
        import librosa
        samples = librosa.resample(samples, orig_sr=sample_rate, target_sr=16000)
    if samples.size == 0:
        return []
    scores, _embeddings, _spectro = model(samples)
    mean_scores = np.asarray(scores).mean(axis=0)
    names = _class_names()
    idx = np.argsort(mean_scores)[::-1][:top_k]
    return [{"class": names[i] if i < len(names) else str(i),
             "score": float(mean_scores[i])} for i in idx]
```

- [ ] **Step 4: Add the optional dep group** to `pyproject.toml` (do NOT add to base `dependencies`):
```toml
[project.optional-dependencies]
ambient = [
    "tensorflow>=2.15",
    "tensorflow-hub>=0.16",
]
```
(Append alongside the existing `analysis`/`dev` groups.)

- [ ] **Step 5: Run the test; confirm 2 passed** (tests mock `_model`, so TF need not be installed for CI):
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
python -m pytest audio_context/test_ambient.py -v
```

- [ ] **Step 6: Confirm fail-soft without TF:**
```bash
python -c "from audio_context.ambient import is_available, classify_ambient; import numpy as np; print('available=', is_available()); print('classify=', classify_ambient(np.zeros(16000,dtype='float32'),16000))"
```
Expected: `available= False` and `classify= []` (TF not installed → graceful).

- [ ] **Step 7: Commit**
```bash
git add apps/inference/audio_context/ambient.py apps/inference/audio_context/test_ambient.py apps/inference/pyproject.toml
git commit -m "feat(audio): YAMNet ambient classifier — lazy, optional dep, fail-soft"
```

> **Enabling ambient** (later, on the 4080 or Mac): `uv pip install ".[ambient]"` from `apps/inference`. Until then `classify_ambient` returns `[]` and the loop simply writes no ambient packets.

---

## Task 7: `audio_social_context` L3 axis

**Files:**
- Create: `apps/inference/fusion/axes/audio_social_context.py`
- Test: `apps/inference/fusion/axes/test_audio_social_context.py`

**Context:** Mirror the existing `fusion/axes/meta_context.py` axis pattern. The axis reads recent `audio_social_context` packets and emits an `AxisEstimate` (`fusion/belief_state.py`) of `{"category": "alone"|"with_other"}`. **Step 0: read `fusion/axes/meta_context.py` first** and match its function shape, how it opens the DB, and how it builds `AxisEstimate` (axis, value, timestamp, confidence, source, meta_context).

- [ ] **Step 1: Write the failing test** `apps/inference/fusion/axes/test_audio_social_context.py`:
```python
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fusion.axes import audio_social_context as asc
from fusion.belief_state import AxisEstimate


class _Cur:
    def __init__(self, rows): self._rows = rows
    def execute(self, *a, **k): pass
    def fetchone(self): return self._rows[0] if self._rows else None
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _Conn:
    def __init__(self, rows): self._rows = rows
    def cursor(self): return _Cur(self._rows)
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_with_other_when_latest_packet_has_other(monkeypatch):
    now = datetime.now(timezone.utc)
    # latest packet payload speaker='both', recorded_at=now
    monkeypatch.setattr(asc, "get_conn",
                        lambda: _Conn([({"speaker": "both"}, now)]))
    est = asc.compute_audio_social_context("u1")
    assert isinstance(est, AxisEstimate)
    assert est.axis == "audio_social_context"
    assert est.value == {"category": "with_other"}


def test_alone_when_latest_self(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(asc, "get_conn",
                        lambda: _Conn([({"speaker": "self"}, now)]))
    est = asc.compute_audio_social_context("u1")
    assert est.value == {"category": "alone"}


def test_none_when_no_packets(monkeypatch):
    monkeypatch.setattr(asc, "get_conn", lambda: _Conn([]))
    assert asc.compute_audio_social_context("u1") is None
```

- [ ] **Step 2: Run it; confirm FAIL.**

- [ ] **Step 3: Create `apps/inference/fusion/axes/audio_social_context.py`:**
```python
"""L3 axis: audio_social_context — is the user alone or with others, by ear."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from db import get_conn  # noqa: E402
from fusion.belief_state import AxisEstimate  # noqa: E402

AXIS = "audio_social_context"
SOURCE = "L3.fusion.audio_social_context"
FRESH_SECONDS = 300


def compute_audio_social_context(user_id: str) -> AxisEstimate | None:
    """Latest audio_social_context packet → alone/with_other estimate, or None."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT payload, recorded_at
            FROM sensor_readings
            WHERE user_id = %s AND kind = 'audio_social_context'
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    payload, recorded_at = row
    speaker = (payload or {}).get("speaker", "none")
    category = "with_other" if speaker in ("other", "both") else "alone"
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    return AxisEstimate(
        axis=AXIS,
        value={"category": category},
        timestamp=recorded_at,
        confidence=0.8,
        source=SOURCE,
        meta_context=None,
        fresh_for_seconds=FRESH_SECONDS,
    )
```
(Adjust `AxisEstimate(...)` kwargs if Step-0 reading of `meta_context.py` shows a different constructor usage — match the sibling exactly.)

- [ ] **Step 4: Run it; confirm 3 passed.**

- [ ] **Step 5: Commit**
```bash
git add apps/inference/fusion/axes/audio_social_context.py apps/inference/fusion/axes/test_audio_social_context.py
git commit -m "feat(fusion): audio_social_context axis (alone / with_other)"
```

---

## Task 8: Unified always-on mic loop — refactor `voice/loop.py`

**Files:**
- Modify: `apps/inference/.../voice/loop.py` (the file is `apps/voice/loop.py`)
- Test: `apps/voice/test_continuous.py`

**Context:** Today `listen_forever` only does wake-word. We add continuous processing on the SAME stream: maintain a rolling buffer; when a speech window closes, run `diarize` → embed → `identify` per speaker → `PrivacyGate.evaluate` → write `audio_social_context` always, and `audio_prosody`/`audio_ambient` only when the gate allows. Keep wake-word + `run_turn` exactly as-is. Factor the per-window decision into a PURE function `process_window(...)` so it's unit-testable without a mic.

- [ ] **Step 0: Read** `apps/voice/loop.py` (current `run_turn` + `listen_forever`) and `apps/inference/audio_context/__init__.py` exports.

- [ ] **Step 1: Write the failing test** `apps/voice/test_continuous.py`:
```python
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

APPS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS))
sys.path.insert(0, str(APPS / "inference"))

from voice.continuous import ContinuousProcessor


def test_self_speech_emits_social_and_prosody(monkeypatch):
    writes = []
    proc = ContinuousProcessor(
        user_id="u1",
        identify_speakers=lambda audio, sr: ["self"],
        prosody_of=lambda audio, sr: {"energy": 0.2, "tone": "calm"},
        ambient_of=lambda audio, sr: [],
        write_social=lambda **k: writes.append(("social", k)),
        write_prosody=lambda **k: writes.append(("prosody", k)),
        write_ambient=lambda **k: writes.append(("ambient", k)),
    )
    now = datetime.now(timezone.utc)
    proc.process_window(np.ones(16000, dtype=np.float32), 16000, vad_active=True, now=now)
    kinds = [w[0] for w in writes]
    assert "social" in kinds and "prosody" in kinds
    assert writes[0][1]["speaker"] == "self"


def test_other_voice_emits_social_only(monkeypatch):
    writes = []
    proc = ContinuousProcessor(
        user_id="u1",
        identify_speakers=lambda audio, sr: ["self", "other"],
        prosody_of=lambda audio, sr: {"energy": 0.2, "tone": "calm"},
        ambient_of=lambda audio, sr: [{"class": "Speech", "score": 0.9}],
        write_social=lambda **k: writes.append(("social", k)),
        write_prosody=lambda **k: writes.append(("prosody", k)),
        write_ambient=lambda **k: writes.append(("ambient", k)),
    )
    now = datetime.now(timezone.utc)
    proc.process_window(np.ones(16000, dtype=np.float32), 16000, vad_active=True, now=now)
    kinds = [w[0] for w in writes]
    assert kinds == ["social"]            # privacy gate suppressed prosody + ambient
    assert writes[0][1]["speaker"] == "both"


def test_silence_emits_ambient(monkeypatch):
    writes = []
    proc = ContinuousProcessor(
        user_id="u1",
        identify_speakers=lambda audio, sr: [],
        prosody_of=lambda audio, sr: {"energy": 0.0, "tone": "flat"},
        ambient_of=lambda audio, sr: [{"class": "Silence", "score": 0.95}],
        write_social=lambda **k: writes.append(("social", k)),
        write_prosody=lambda **k: writes.append(("prosody", k)),
        write_ambient=lambda **k: writes.append(("ambient", k)),
    )
    now = datetime.now(timezone.utc)
    proc.process_window(np.zeros(16000, dtype=np.float32), 16000, vad_active=False, now=now)
    kinds = [w[0] for w in writes]
    assert "ambient" in kinds and "prosody" not in kinds
```

- [ ] **Step 2: Run it; confirm FAIL** (no `voice.continuous`).

- [ ] **Step 3: Create `apps/voice/continuous.py`:**
```python
"""Continuous-audio processing: one window → privacy-gated semantic packets.

Pure orchestration with injectable I/O (identify/prosody/ambient/writers) so it
unit-tests without a mic, DB, or models. listen_continuous() wires the real ones.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np

APPS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS_DIR))
sys.path.insert(0, str(APPS_DIR / "inference"))

from audio_context.privacy import PrivacyGate  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


class ContinuousProcessor:
    """Applies the privacy gate to one audio window and emits the allowed packets."""

    def __init__(
        self,
        *,
        user_id: str = DEFAULT_USER_ID,
        identify_speakers: Callable[[np.ndarray, int], list[str]],
        prosody_of: Callable[[np.ndarray, int], dict[str, Any]],
        ambient_of: Callable[[np.ndarray, int], list[dict]],
        write_social: Callable[..., Any],
        write_prosody: Callable[..., Any],
        write_ambient: Callable[..., Any],
        buffer_seconds: float = 30.0,
    ) -> None:
        self.user_id = user_id
        self.identify_speakers = identify_speakers
        self.prosody_of = prosody_of
        self.ambient_of = ambient_of
        self.write_social = write_social
        self.write_prosody = write_prosody
        self.write_ambient = write_ambient
        self.gate = PrivacyGate(buffer_seconds=buffer_seconds)

    def process_window(self, audio: np.ndarray, sample_rate: int, *,
                       vad_active: bool, now: datetime) -> None:
        speakers = self.identify_speakers(audio, sample_rate) if vad_active else []
        decision = self.gate.evaluate(speakers=speakers, now=now)

        self.write_social(
            user_id=self.user_id, recorded_at=now,
            speaker=decision.social_context,
            num_speakers=len(set(speakers)),
            vad_active=vad_active,
        )

        if decision.allow_prosody and vad_active:
            self.write_prosody(user_id=self.user_id, recorded_at=now,
                               prosody=self.prosody_of(audio, sample_rate))

        if decision.allow_ambient and not vad_active:
            classes = self.ambient_of(audio, sample_rate)
            if classes:
                self.write_ambient(user_id=self.user_id, recorded_at=now, top_classes=classes)
```

- [ ] **Step 4: Run the test; confirm 3 passed.**

- [ ] **Step 5: Add the real wiring** to `apps/voice/loop.py` — a `listen_continuous()` that builds a `ContinuousProcessor` from the real modules and folds it into the wake-word mic loop. Append this function (and keep `listen_forever` for wake-word-only use):
```python
def listen_continuous(
    *,
    user_id: str = DEFAULT_USER_ID,
    wake_word: str | None = None,
    sample_rate: int = 16000,
    block_seconds: float = 0.08,
    window_seconds: float = 3.0,
) -> None:
    """ONE always-on mic loop: wake-word + continuous privacy-gated semantics."""
    import os

    import numpy as np
    import sounddevice as sd

    from audio_context import speaker_id
    from audio_context.ambient import classify_ambient
    from audio_context.diarization import diarize
    from audio_context.prosody import extract_prosody
    from audio_context.vad import detect_voice_activity
    from voice.continuous import ContinuousProcessor
    from voice import loop as _self
    from wake_word import VoiceWakeWordDetector

    centroid = speaker_id.load_centroid(user_id)

    def identify_speakers(audio, sr):
        segs = diarize(audio, sr)
        ids = set()
        for s in segs:
            i0 = int(s["start_seconds"] * sr); i1 = int(s["end_seconds"] * sr)
            emb = speaker_id.embed_utterance(audio[i0:i1], sr)
            ids.add("unknown" if emb is None else speaker_id.identify(emb, centroid=centroid))
        return sorted(ids)

    proc = ContinuousProcessor(
        user_id=user_id,
        identify_speakers=identify_speakers,
        prosody_of=lambda a, sr: extract_prosody(a, sr).to_dict(),
        ambient_of=lambda a, sr: classify_ambient(a, sr),
        write_social=_social_writer,
        write_prosody=_prosody_writer,
        write_ambient=_ambient_writer,
    )

    ww = wake_word or os.environ.get("DAYBOOK_WAKE_WORD", "hey_jarvis")
    detector = VoiceWakeWordDetector(wake_word=ww, sample_rate=sample_rate)
    block_frames = int(sample_rate * block_seconds)
    window_frames = int(sample_rate * window_seconds)
    buf: list[np.ndarray] = []

    from datetime import datetime, timezone
    print(f"Always-on: wake-word {ww!r} + continuous semantics. Ctrl-C to stop.", flush=True)
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32",
                        blocksize=block_frames) as stream:
        while True:
            audio, _ = stream.read(block_frames)
            chunk = np.asarray(audio[:, 0], dtype=np.float32)

            event = detector.process_audio_chunk(chunk, sample_rate=sample_rate)
            if event is not None:
                detector.reset()
                run_turn(user_id=user_id)
                buf.clear()
                continue

            buf.append(chunk)
            if sum(c.size for c in buf) >= window_frames:
                window = np.concatenate(buf); buf.clear()
                vad_active = len(detect_voice_activity(window, sample_rate)) > 0
                proc.process_window(window, sample_rate, vad_active=vad_active,
                                    now=datetime.now(timezone.utc))
```
Add these thin writer adapters near the top of `loop.py` (they bind the `audio_context.writer` functions to the keyword shape `ContinuousProcessor` expects):
```python
def _social_writer(*, user_id, recorded_at, speaker, num_speakers, vad_active):
    from audio_context.writer import write_social_context
    return write_social_context(user_id, recorded_at, speaker=speaker,
                                num_speakers=num_speakers, vad_active=vad_active)


def _prosody_writer(*, user_id, recorded_at, prosody):
    from audio_context.writer import write_prosody
    return write_prosody(user_id, recorded_at, prosody)


def _ambient_writer(*, user_id, recorded_at, top_classes):
    from audio_context.writer import write_ambient
    return write_ambient(user_id, recorded_at, top_classes)
```

- [ ] **Step 6: Verify loop imports + continuous test still green:**
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
python -m pytest voice/ -q
python -c "import sys; sys.path.insert(0,'.'); sys.path.insert(0,'inference'); from voice.loop import listen_continuous; print('listen_continuous imports OK')"
```
Expected: voice tests pass; import OK.

- [ ] **Step 7: Commit**
```bash
git add apps/voice/continuous.py apps/voice/test_continuous.py apps/voice/loop.py
git commit -m "feat(voice): unified always-on loop — wake-word + privacy-gated continuous semantics"
```

---

## Task 9: CLI flag + docs + theory-aligner + tag

**Files:**
- Modify: `apps/voice/cli.py`, `docs/ARCHITECTURE.md`, `docs/STATUS.md`

- [ ] **Step 1: Add a `--continuous` flag** to `apps/voice/cli.py` so the bare run can choose wake-word-only (`listen_forever`) vs always-on (`listen_continuous`). In `main()`, add `p.add_argument("--continuous", action="store_true", help="Always-on: wake-word + continuous semantics.")` and branch:
```python
    if args.continuous:
        from voice.loop import listen_continuous
        listen_continuous(user_id=args.user_id)
        return 0
    listen_forever(user_id=args.user_id)
    return 0
```

- [ ] **Step 2: Full suite + smokes:**
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
python -m pytest audio_context/ fusion/ features/ -q
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
python -m pytest wisp/ voice/ -q
python -m voice.smoke_test
cd inference && python -m fusion.smoke_test
```
Expected: all green.

- [ ] **Step 3: Update `docs/ARCHITECTURE.md`** — extend the Layer 1/2/3 + §11 (semantic-first sensing) notes: continuous mic produces semantic packets (`audio_social_context`/`audio_prosody`/`audio_ambient`), raw audio discarded; Privacy Policy #1 enforced at the gate; `audio_social_context` axis live. Note YAMNet is the triggered-escalation-free continuous ambient read (commitment #11) and is optional/lazy.

- [ ] **Step 4: Update `docs/STATUS.md`** — date `2026-05-28`; Week 3 section: continuous mic pipeline, speaker enrollment, privacy gate, 3 new packet kinds, `audio_social_context` axis live (now 3 of ~6 axes); follow-ups (enroll Aakash's voice; `pip install .[ambient]` to enable YAMNet; EEG stretch still pending hardware).

- [ ] **Step 5: Commit docs**
```bash
git add apps/voice/cli.py docs/ARCHITECTURE.md docs/STATUS.md
git commit -m "docs: Week 3 continuous mic — ARCHITECTURE + STATUS; cli --continuous"
```

- [ ] **Step 6: Theory-aligner gate** (standing rule). Dispatch `theory-aligner` on the branch — verify commitments #10 (intent×modality — continuous is the Continuous-intent / Audio-modality path), #11 (semantic-first; raw audio discarded), #14 (meta-context bias), and that Privacy Policy #1 is actually enforced in code. Apply blocker/should-fix findings (own verification) before tag.

- [ ] **Step 7: PR, merge, tag**
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git push -u origin feat/week-3-continuous-mic
gh pr create --title "Week 3 — continuous mic semantic pipeline" --body "VAD + speaker-ID + prosody + YAMNet ambient on one always-on mic loop, Privacy Policy #1 enforced. audio_social_context axis live."
# after merge:
git checkout main && git pull --ff-only || git reset --hard origin/main
git tag -a mvp-week-3-end -m "Week 3: continuous mic semantic pipeline"
git push origin mvp-week-3-end
```

---

## Notes / follow-ups (log, don't silently absorb)

- **Manual: enroll Aakash's voice** (record 3–5 clips → `speaker_id.enroll`). Until then `identify` returns `'unknown'`, and the privacy gate conservatively treats unknown as `'other'` → continuous semantics stay suppressed (fail-safe, but means no prosody until enrolled).
- **YAMNet off by default** — `pip install .[ambient]` to enable; loop writes no ambient packets until then.
- **EEG stretch deferred** — BioAmp wiring + `capture/eeg.py` + `cognitive_load` axis when the pill is in hand.
- **Window cadence** (`window_seconds=3.0`) and `fresh_for_seconds` are first-guess; tune once living with it. The 30s privacy buffer is the locked §5 value.
- **diarize cost:** resemblyzer embeds per 1.5s window — on Mac CPU this is fine for 3s windows but watch latency; route to the 4080 with embeddings later if needed.
