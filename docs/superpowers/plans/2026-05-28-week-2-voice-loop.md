# Week 2 — State-Aware Voice Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the voice loop on the post-scrap codebase — wake-word → STT → `compose_utterance()` → TTS — with the composer reading the **freshness-gated BeliefState** before generating, so Regis's spoken reply is shaped by the user's current inferred state.

**Architecture:** The composer (`apps/wisp/composer.py`) is already the turn engine. We (1) re-pull the audio/STT/wake-word primitives from the `v0-pre-rebuild` tag into `apps/inference/`, (2) add a DB→BeliefState loader and rewire the composer's state read through it (freshness gated), (3) replace the composer's `gather_substrate()` stub with a real impl, and (4) add a thin `apps/voice/` runtime that orchestrates the loop. TTS ships on the zero-dependency macOS `say` backend first; kokoro is optional. The wake-word ships on the built-in `hey_jarvis` placeholder until the custom "Hey Regis" model is trained.

**Tech Stack:** Python 3.11, `sounddevice`/`soundfile` (audio I/O), `faster-whisper` (streaming STT), `openwakeword` + `onnxruntime` (wake word), macOS `say` (TTS fallback), existing `ChatClient` (Codex/gpt-5.2), Neon Postgres (`user_state_estimate` per-axis rows).

**Conventions (from CLAUDE.md):** run from `apps/` with `apps/inference/.venv` active; `from db import get_conn` after the `sys.path` bootstrap; tz-aware UTC datetimes; `DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"`; one-line docstrings; `from __future__ import annotations`. Run smoke tests from the directory whose package you're testing (e.g. `cd apps/inference && python -m audio.smoke_test`; `cd apps && python -m voice.smoke_test`).

**Pre-flight (run once before Task 1):**
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git checkout main && git pull
git checkout -b feat/week-2-voice-loop
source apps/inference/.venv/bin/activate
```

---

## Task 1: Re-pull TTS audio package + add audio deps

**Files:**
- Restore from tag: `apps/inference/audio/{__init__,player,streaming,tts_router,kokoro_tts,say_tts,smoke_test}.py`
- Modify: `apps/inference/pyproject.toml`

- [ ] **Step 1: Restore the audio package from the tag**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git checkout v0-pre-rebuild -- apps/inference/audio/
git status --short apps/inference/audio/
```
Expected: the 8 audio files listed as added (`A`) / staged.

- [ ] **Step 2: Add audio dependencies to pyproject**

Edit `apps/inference/pyproject.toml`. The current `dependencies` array is:
```toml
dependencies = [
    "numpy>=1.26.0",
]
```
Replace it with:
```toml
dependencies = [
    "numpy>=1.26.0",
    "sounddevice>=0.4.6",
    "soundfile>=0.12.1",
]
```
(`say_tts` uses the macOS `say` binary — no Python dep. `kokoro-onnx` stays out for now; `tts_router` auto-falls-back to `say` when kokoro is unavailable.)

- [ ] **Step 3: Install the new deps into the venv**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
source .venv/bin/activate
uv pip install "sounddevice>=0.4.6" "soundfile>=0.12.1"
```
Expected: both install without error.

- [ ] **Step 4: Verify the TTS backend resolves to `say`**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
python -c "from audio.tts_router import get_active_backend; print('backend=', get_active_backend())"
```
Expected: `backend= say` (kokoro absent → macOS `say` fallback).

- [ ] **Step 5: Run the audio smoke test with playback suppressed**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
DAYBOOK_NO_PLAY=1 python -m audio.smoke_test
```
Expected: smoke test passes (synthesis succeeds; `DAYBOOK_NO_PLAY=1` skips speaker output so it runs headless). If the smoke test asserts playback, note the failure and re-run once without `DAYBOOK_NO_PLAY` on the dev Mac to confirm audio actually plays.

- [ ] **Step 6: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/inference/audio/ apps/inference/pyproject.toml
git commit -m "feat(voice): re-pull TTS audio package from v0-pre-rebuild + audio deps"
```

---

## Task 2: Re-pull STT modules + verify import-clean

**Files:**
- Restore from tag: `apps/inference/llm/stt.py`, `apps/inference/llm/stt_streaming.py`
- Modify: `apps/inference/pyproject.toml`

- [ ] **Step 1: Restore the STT modules from the tag**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git checkout v0-pre-rebuild -- apps/inference/llm/stt.py apps/inference/llm/stt_streaming.py
```

- [ ] **Step 2: Add the streaming-STT dependency**

Edit `apps/inference/pyproject.toml` `dependencies` to append `faster-whisper`:
```toml
    "faster-whisper>=1.0.0",
```
(`stt_streaming.py` defaults to `faster-whisper` `small.en`/`int8`. `stt.py` uses `recall.whisper_client`, which uses `openai-whisper` — already installed for the recall wedge; do not remove it.)

- [ ] **Step 3: Install faster-whisper**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
source .venv/bin/activate
uv pip install "faster-whisper>=1.0.0"
```
Expected: installs cleanly.

- [ ] **Step 4: Verify both STT modules import and the streaming backend resolves**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
python -c "import llm.stt, llm.stt_streaming as s; print('stt ok; streaming backend=', s.get_streaming_backend())"
```
Expected: prints `stt ok; streaming backend= faster-whisper` (or the configured backend). No ImportError — confirms `from recall.whisper_client import transcribe` still resolves on current main.

- [ ] **Step 5: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/inference/llm/stt.py apps/inference/llm/stt_streaming.py apps/inference/pyproject.toml
git commit -m "feat(voice): re-pull STT modules (stt + stt_streaming) + faster-whisper dep"
```

---

## Task 3: Re-pull wake-word detector (detector + intent only, NOT handlers)

**Files:**
- Restore from tag: `apps/inference/wake_word/{__init__,detector,command_intent,smoke_test}.py`, `apps/inference/wake_word/training/README.md`, `apps/inference/wake_word/models/.gitkeep`
- Modify: `apps/inference/pyproject.toml`

- [ ] **Step 1: Restore only the safe wake-word files (handlers.py is excluded — it imports the removed `gesture.recorder`)**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git checkout v0-pre-rebuild -- \
  apps/inference/wake_word/__init__.py \
  apps/inference/wake_word/detector.py \
  apps/inference/wake_word/command_intent.py \
  apps/inference/wake_word/smoke_test.py \
  apps/inference/wake_word/training/README.md \
  apps/inference/wake_word/models/.gitkeep
ls apps/inference/wake_word/
```
Expected: `__init__.py detector.py command_intent.py smoke_test.py training/ models/` — and **no** `handlers.py`.

- [ ] **Step 2: Confirm `__init__.py` does not import handlers**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
grep -n "handlers" apps/inference/wake_word/__init__.py || echo "OK: __init__ does not import handlers"
```
Expected: `OK: __init__ does not import handlers`. (Verified at planning time — `__init__` imports only `command_intent` and `detector`.) If it DOES import handlers, edit `__init__.py` to remove that import line and the corresponding `__all__` entries.

- [ ] **Step 3: Add wake-word dependencies**

Edit `apps/inference/pyproject.toml` `dependencies` to append:
```toml
    "openwakeword>=0.6.0",
    "onnxruntime>=1.17.0",
```

- [ ] **Step 4: Install wake-word deps**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
source .venv/bin/activate
uv pip install "openwakeword>=0.6.0" "onnxruntime>=1.17.0"
```
Expected: installs cleanly.

- [ ] **Step 5: Verify import + intent classifier behavior (no mic needed)**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
python -c "from wake_word import VoiceWakeWordDetector, classify_intent, CommandIntent; \
print('dismiss=', classify_intent('stop')); \
print('msg=', classify_intent('Regis, how am I feeling today after that long session'))"
```
Expected: `dismiss= CommandIntent.DISMISS` and `msg= CommandIntent.NONE` (long utterance routes to chat).

- [ ] **Step 6: Run the wake-word smoke test (model download may occur on first run)**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
python -m wake_word.smoke_test
```
Expected: passes. First run may download the built-in `hey_jarvis` openWakeWord model (network). If the smoke test requires a live mic and there is none in CI, note that it must be run on the dev Mac.

- [ ] **Step 7: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/inference/wake_word/ apps/inference/pyproject.toml
git commit -m "feat(voice): re-pull wake-word detector + intent (handlers deferred, needs gesture/)"
```

---

## Task 4: `fusion/loader.py` — load freshness-gated BeliefState from DB

**Files:**
- Create: `apps/inference/fusion/loader.py`
- Test: `apps/inference/fusion/test_loader.py`

- [ ] **Step 1: Write the failing test**

Create `apps/inference/fusion/test_loader.py`:
```python
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fusion.belief_state import BeliefState
from fusion.loader import load_belief_state


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_a, **_k):
        return None

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def test_load_belief_state_builds_axis_estimates(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [
        # (axis, value, confidence, source, timestamp, meta_context, i_model_id)
        ("meta_context", {"category": "waking/focused"}, 0.8, "L3.fusion.meta_context", now, "waking/focused", None),
        ("sleep_stage", {"label": "rem", "prob": 0.7}, 0.7, "classifier.binary_rem", now, None, None),
    ]
    monkeypatch.setattr("fusion.loader.get_conn", lambda: _FakeConn(rows))

    belief = load_belief_state("user-123", now=now)

    assert isinstance(belief, BeliefState)
    assert belief.user_id == "user-123"
    meta = belief.get("meta_context", now=now)
    assert meta is not None
    assert meta.value == {"category": "waking/focused"}
    assert meta.source == "L3.fusion.meta_context"
    assert meta.meta_context == "waking/focused"


def test_load_belief_state_empty_returns_empty_belief(monkeypatch):
    monkeypatch.setattr("fusion.loader.get_conn", lambda: _FakeConn([]))
    belief = load_belief_state("user-123")
    assert isinstance(belief, BeliefState)
    assert belief.estimates == {}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
python -m pytest fusion/test_loader.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'fusion.loader'`.

- [ ] **Step 3: Write the minimal implementation**

Create `apps/inference/fusion/loader.py`:
```python
"""Load the current per-user BeliefState from user_state_estimate rows."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import get_conn  # noqa: E402

from .belief_state import AxisEstimate, BeliefState


def load_belief_state(user_id: str, *, now: datetime | None = None) -> BeliefState:
    """Latest per-axis row → AxisEstimate, bundled into a BeliefState.

    Freshness is NOT filtered here — callers use BeliefState.get()/snapshot(),
    which apply each axis's freshness gate. `now` is accepted for test
    determinism and forwarded nowhere (estimates carry their own timestamps).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    belief = BeliefState(user_id=user_id)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (axis)
                axis, value, confidence, source, timestamp, meta_context, i_model_id
            FROM user_state_estimate
            WHERE user_id = %s
            ORDER BY axis, timestamp DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    for axis, value, confidence, source, ts, meta_context, i_model_id in rows:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        belief.update(
            AxisEstimate(
                axis=axis,
                value=value if isinstance(value, dict) else {"value": value},
                timestamp=ts,
                confidence=confidence,
                source=source or "unknown",
                meta_context=meta_context,
                i_model_id=str(i_model_id) if i_model_id is not None else None,
            )
        )
    return belief
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
python -m pytest fusion/test_loader.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/inference/fusion/loader.py apps/inference/fusion/test_loader.py
git commit -m "feat(fusion): load_belief_state — DB per-axis rows -> freshness-gated BeliefState"
```

---

## Task 5: Rewire composer state read through the freshness-gated BeliefState

**Files:**
- Modify: `apps/wisp/composer.py` (`_read_latest_state`, lines ~258-290)
- Test: `apps/wisp/test_composer_state.py`

- [ ] **Step 1: Write the failing test**

Create `apps/wisp/test_composer_state.py`:
```python
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

APPS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS))
sys.path.insert(0, str(APPS / "inference"))

import wisp.composer as composer
from fusion.belief_state import AxisEstimate, BeliefState


def test_read_latest_state_drops_stale_axes(monkeypatch):
    now = datetime.now(timezone.utc)
    belief = BeliefState(user_id="u1")
    belief.update(AxisEstimate(
        axis="meta_context",
        value={"category": "waking/focused"},
        timestamp=now,
        confidence=0.9,
        source="L3.fusion.meta_context",
        meta_context="waking/focused",
        fresh_for_seconds=300,
    ))
    belief.update(AxisEstimate(
        axis="sleep_stage",
        value={"label": "rem"},
        timestamp=now - timedelta(hours=6),   # stale
        confidence=0.7,
        source="classifier.binary_rem",
        fresh_for_seconds=300,
    ))
    monkeypatch.setattr(composer, "load_belief_state", lambda user_id: belief)

    state = composer._read_latest_state("u1")
    assert state is not None
    assert "meta_context" in state
    assert "sleep_stage" not in state          # gated out by freshness
    assert state["meta_context"]["value"] == {"category": "waking/focused"}


def test_read_latest_state_none_when_all_stale(monkeypatch):
    now = datetime.now(timezone.utc)
    belief = BeliefState(user_id="u1")
    belief.update(AxisEstimate(
        axis="meta_context",
        value={"category": "waking"},
        timestamp=now - timedelta(days=1),
        confidence=0.5,
        source="x",
        fresh_for_seconds=300,
    ))
    monkeypatch.setattr(composer, "load_belief_state", lambda user_id: belief)
    assert composer._read_latest_state("u1") is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
python -m pytest wisp/test_composer_state.py -v
```
Expected: FAIL — `AttributeError: module 'wisp.composer' has no attribute 'load_belief_state'` (the symbol isn't imported yet).

- [ ] **Step 3: Add the import near the top of `apps/wisp/composer.py`**

Find the existing inference-path bootstrap + imports block in `composer.py` (it already does `sys.path.insert(... "inference")` and imports `from db import get_conn`). Add alongside those imports:
```python
from fusion.loader import load_belief_state  # noqa: E402
```

- [ ] **Step 4: Replace the body of `_read_latest_state`**

Replace the entire current `_read_latest_state` function (the one doing the raw `SELECT DISTINCT ON (axis) ...`) with:
```python
def _read_latest_state(user_id: str) -> dict[str, Any] | None:
    """Current per-axis state, FRESHNESS-GATED via the L3 BeliefState.

    Stale axes (past their per-axis fresh_for_seconds) are dropped so Regis
    never speaks from data that no longer reflects the user. Shape preserved
    for _build_user_prompt: {axis: {value, confidence, source, timestamp, meta_context}}.
    """
    belief = load_belief_state(user_id)
    now = datetime.now(timezone.utc)
    out: dict[str, Any] = {}
    for axis, est in belief.estimates.items():
        if not est.is_fresh(now=now):
            continue
        out[axis] = {
            "value": est.value,
            "confidence": est.confidence,
            "source": est.source,
            "timestamp": est.timestamp.isoformat(),
            "meta_context": est.meta_context,
        }
    return out or None
```
(Confirm `datetime`/`timezone` are already imported in `composer.py`; they are used elsewhere in the file. If not, add `from datetime import datetime, timezone`.)

- [ ] **Step 5: Run the test to verify it passes**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
python -m pytest wisp/test_composer_state.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/wisp/composer.py apps/wisp/test_composer_state.py
git commit -m "feat(wisp): composer reads freshness-gated BeliefState (was raw latest rows)"
```

---

## Task 6: Replace `gather_substrate()` stub with a real impl

**Files:**
- Modify: `apps/wisp/composer.py` (`gather_substrate`, ~line 56; `SubstrateContext` ~line 41)
- Test: `apps/wisp/test_substrate.py`

**Context:** `SubstrateContext` fields (from composer.py): `current_prosody`, `regis_traits: dict[str,float]`, `regis_self`, `active_i_models`, `relevant_observations: list[dict]`, `active_i_model_cluster_ids`, `primary_i_model_cluster_id`, `current_user_state: dict | None`. Week 2 fills the cheap, available ones: `relevant_observations` (from `regis_observations`), `regis_traits` (latest per-trait from `regis_trait_history`), and `current_user_state` (from `_read_latest_state`). The rest stay at their empty defaults (I-Model self-expansion is post-MVP, commitment #6).

- [ ] **Step 1: Write the failing test**

Create `apps/wisp/test_substrate.py`:
```python
from __future__ import annotations

import sys
from pathlib import Path

APPS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS))
sys.path.insert(0, str(APPS / "inference"))

import wisp.composer as composer


def test_gather_substrate_populates_observations_and_traits(monkeypatch):
    monkeypatch.setattr(composer, "_read_recent_observations",
                        lambda user_id, limit: [{"content": "prefers brevity"}])
    monkeypatch.setattr(composer, "_read_current_traits",
                        lambda user_id: {"warmth": 0.6, "dryness": 0.7})
    monkeypatch.setattr(composer, "_read_latest_state",
                        lambda user_id: {"meta_context": {"value": {"category": "waking/focused"}}})

    ctx = composer.gather_substrate(user_id="u1")

    assert ctx.relevant_observations == [{"content": "prefers brevity"}]
    assert ctx.regis_traits == {"warmth": 0.6, "dryness": 0.7}
    assert ctx.current_user_state == {"meta_context": {"value": {"category": "waking/focused"}}}


def test_gather_substrate_tolerates_empty(monkeypatch):
    monkeypatch.setattr(composer, "_read_recent_observations", lambda user_id, limit: [])
    monkeypatch.setattr(composer, "_read_current_traits", lambda user_id: {})
    monkeypatch.setattr(composer, "_read_latest_state", lambda user_id: None)
    ctx = composer.gather_substrate(user_id="u1")
    assert ctx.relevant_observations == []
    assert ctx.regis_traits == {}
    assert ctx.current_user_state is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
python -m pytest wisp/test_substrate.py -v
```
Expected: FAIL — `AttributeError: ... has no attribute '_read_recent_observations'`.

- [ ] **Step 3: Implement the two readers + real `gather_substrate`**

In `apps/wisp/composer.py`, replace the stub:
```python
def gather_substrate(*, user_id: str, query_embedding: Any = None) -> SubstrateContext:  # noqa: ARG001
    return SubstrateContext()
```
with:
```python
def _read_recent_observations(user_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Most recent regis_observations for this user."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT content, created_at
            FROM regis_observations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = cur.fetchall()
    return [{"content": r[0], "created_at": r[1].isoformat() if r[1] else None} for r in rows]


def _read_current_traits(user_id: str) -> dict[str, float]:
    """Latest value per Regis trait from regis_trait_history."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (trait_name) trait_name, value
            FROM regis_trait_history
            WHERE user_id = %s
            ORDER BY trait_name, changed_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    return {r[0]: float(r[1]) for r in rows}


def gather_substrate(*, user_id: str, query_embedding: Any = None) -> SubstrateContext:  # noqa: ARG001
    """Assemble the context Regis composes from: observations, traits, current state.

    I-Model fields stay at empty defaults until self-expansion (#6) lands.
    """
    return SubstrateContext(
        relevant_observations=_read_recent_observations(user_id),
        regis_traits=_read_current_traits(user_id),
        current_user_state=_read_latest_state(user_id),
    )
```

> **Verify column names before running:** this assumes `regis_observations(content, created_at, user_id)` and `regis_trait_history(trait_name, value, changed_at, user_id)`. Confirm with:
> ```bash
> cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
> python -c "from db import get_conn; \
> c=get_conn().cursor(); \
> c.execute(\"select column_name from information_schema.columns where table_name='regis_observations'\"); print('obs:', [r[0] for r in c.fetchall()]); \
> c.execute(\"select column_name from information_schema.columns where table_name='regis_trait_history'\"); print('traits:', [r[0] for r in c.fetchall()])"
> ```
> Adjust the two SELECTs if the live columns differ (e.g. `body` instead of `content`, `created_at` instead of `changed_at`). The TS source of truth (`packages/shared/src/types.ts`) names trait fields `traitName`/`value`/`changedAt` → DB snake_case `trait_name`/`value`/`changed_at`.

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
python -m pytest wisp/test_substrate.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Run the existing composer smoke test (live LLM + DB) to confirm no regression**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
python -m wisp.smoke_test
```
Expected: composer end-to-end passes; substrate now carries real observations/traits. If it fails on a DB column name, fix per the Step-3 verification note and re-run.

- [ ] **Step 6: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/wisp/composer.py apps/wisp/test_substrate.py
git commit -m "feat(wisp): real gather_substrate (observations + traits + current state)"
```

---

## Task 7: `apps/voice/loop.py` — the orchestrator (testable, hardware-injectable)

**Files:**
- Create: `apps/voice/__init__.py`, `apps/voice/loop.py`
- Test: `apps/voice/test_loop.py`

**Design:** `run_turn()` takes injectable callables (`transcribe`, `compose`, `speak_fn`) so it is fully unit-testable with no mic/speaker/LLM. `listen_forever()` wires the real `VoiceWakeWordDetector` + mic and calls `run_turn` on each wake. A "dismiss"/"stop" intent short-circuits (no compose, no speak).

- [ ] **Step 1: Write the failing test**

Create `apps/voice/test_loop.py`:
```python
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

APPS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS))
sys.path.insert(0, str(APPS / "inference"))

from voice.loop import run_turn


@dataclass
class _FakeComposed:
    text: str
    mode: str


def test_run_turn_speaks_composed_reply():
    spoken = {}

    def fake_compose(**kwargs):
        assert kwargs["explicit_context"] == "Regis how am I doing today really"
        return _FakeComposed(text="You're holding steady.", mode="companion")

    def fake_speak(text, *, mode):
        spoken["text"] = text
        spoken["mode"] = mode

    result = run_turn(
        user_id="u1",
        transcribe=lambda: "Regis how am I doing today really",
        compose=fake_compose,
        speak_fn=fake_speak,
    )

    assert result.spoken is True
    assert result.utterance_text == "You're holding steady."
    assert result.mode == "companion"
    assert spoken == {"text": "You're holding steady.", "mode": "companion"}


def test_run_turn_dismiss_short_circuits():
    called = {"composed": False, "spoke": False}

    def fake_compose(**kwargs):
        called["composed"] = True
        return _FakeComposed(text="x", mode="companion")

    def fake_speak(text, *, mode):
        called["spoke"] = True

    result = run_turn(
        user_id="u1",
        transcribe=lambda: "stop",
        compose=fake_compose,
        speak_fn=fake_speak,
    )

    assert result.spoken is False
    assert result.intent == "dismiss"
    assert called == {"composed": False, "spoke": False}


def test_run_turn_empty_transcript_no_compose():
    result = run_turn(
        user_id="u1",
        transcribe=lambda: "   ",
        compose=lambda **k: _FakeComposed("x", "companion"),
        speak_fn=lambda text, *, mode: None,
    )
    assert result.spoken is False
    assert result.transcript == ""
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
python -m pytest voice/test_loop.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'voice'`.

- [ ] **Step 3: Create the package init**

Create `apps/voice/__init__.py`:
```python
"""Waking-empath voice runtime: wake-word -> STT -> compose -> TTS."""
from __future__ import annotations

from .loop import TurnResult, run_turn

__all__ = ["TurnResult", "run_turn"]
```

- [ ] **Step 4: Write the orchestrator**

Create `apps/voice/loop.py`:
```python
"""Wake-word -> STT -> compose_utterance() -> TTS, with injectable I/O for tests."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

APPS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS_DIR))
sys.path.insert(0, str(APPS_DIR / "inference"))

from wake_word import CommandIntent, classify_intent  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
DEFAULT_MOMENT_KIND = "conversation_tease"


@dataclass
class TurnResult:
    transcript: str
    intent: str
    spoken: bool
    utterance_text: str | None
    mode: str | None


def _default_transcribe() -> str:
    from llm.stt_streaming import transcribe_streaming
    return transcribe_streaming()


def _default_compose(**kwargs: Any):
    from wisp.composer import compose_utterance
    return compose_utterance(**kwargs)


def _default_speak(text: str, *, mode: str) -> None:
    from audio.tts_router import speak
    speak(text, mode=mode)


def run_turn(
    *,
    user_id: str = DEFAULT_USER_ID,
    moment_kind: str = DEFAULT_MOMENT_KIND,
    transcribe: Callable[[], str] = _default_transcribe,
    compose: Callable[..., Any] = _default_compose,
    speak_fn: Callable[..., None] = _default_speak,
) -> TurnResult:
    """One full turn: capture speech, route, compose if it's a message, speak."""
    transcript = (transcribe() or "").strip()
    if not transcript:
        return TurnResult("", CommandIntent.NONE.value, False, None, None)

    intent = classify_intent(transcript)
    if intent in (CommandIntent.DISMISS, CommandIntent.SCRATCH_THAT):
        return TurnResult(transcript, intent.value, False, None, None)

    composed = compose(
        user_id=user_id,
        moment_kind=moment_kind,
        explicit_context=transcript,
        retrieval_query=transcript,
    )
    speak_fn(composed.text, mode=composed.mode)
    return TurnResult(transcript, intent.value, True, composed.text, composed.mode)


def listen_forever(
    *,
    user_id: str = DEFAULT_USER_ID,
    wake_word: str | None = None,
    sample_rate: int = 16000,
    block_seconds: float = 0.08,
) -> None:
    """Block on the mic; on each wake-word, run one turn. Ctrl-C to stop."""
    import os

    import numpy as np
    import sounddevice as sd

    from wake_word import VoiceWakeWordDetector

    ww = wake_word or os.environ.get("DAYBOOK_WAKE_WORD", "hey_jarvis")
    detector = VoiceWakeWordDetector(wake_word=ww, sample_rate=sample_rate)
    block_frames = int(sample_rate * block_seconds)

    print(f"Listening for wake-word {ww!r}. Ctrl-C to stop.", flush=True)
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="float32",
                        blocksize=block_frames) as stream:
        while True:
            audio, _ = stream.read(block_frames)
            chunk = np.asarray(audio[:, 0], dtype=np.float32)
            event = detector.process_audio_chunk(chunk, sample_rate=sample_rate)
            if event is None:
                continue
            print(f"[wake @ {event.confidence:.2f}] listening...", flush=True)
            detector.reset()
            result = run_turn(user_id=user_id)
            print(f"  -> intent={result.intent} spoken={result.spoken}", flush=True)
```

- [ ] **Step 5: Run the test to verify it passes**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
python -m pytest voice/test_loop.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/voice/__init__.py apps/voice/loop.py apps/voice/test_loop.py
git commit -m "feat(voice): run_turn orchestrator (wake->STT->compose->TTS, injectable I/O)"
```

---

## Task 8: `apps/voice/cli.py` + `apps/voice/smoke_test.py`

**Files:**
- Create: `apps/voice/cli.py`, `apps/voice/smoke_test.py`

- [ ] **Step 1: Write the CLI**

Create `apps/voice/cli.py`:
```python
"""Run the voice loop. `python -m voice.cli` (mic) or `--once --text "..."` (no mic)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice.loop import DEFAULT_USER_ID, listen_forever, run_turn  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(prog="voice", description="Daybook waking-empath voice loop.")
    p.add_argument("--user-id", default=DEFAULT_USER_ID)
    p.add_argument("--once", action="store_true", help="Run a single turn then exit.")
    p.add_argument("--text", default=None, help="With --once: skip the mic, use this text as the transcript.")
    args = p.parse_args()

    if args.once:
        kwargs = {}
        if args.text is not None:
            kwargs["transcribe"] = lambda: args.text
        result = run_turn(user_id=args.user_id, **kwargs)
        print(f"transcript={result.transcript!r} intent={result.intent} "
              f"spoken={result.spoken} mode={result.mode}")
        if result.utterance_text:
            print(f"Regis: {result.utterance_text}")
        return 0

    listen_forever(user_id=args.user_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write the smoke test (no hardware, no live LLM)**

Create `apps/voice/smoke_test.py`:
```python
"""End-to-end voice-loop smoke with mocked mic/compose/TTS. No hardware needed."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

APPS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS))
sys.path.insert(0, str(APPS / "inference"))

from voice.loop import run_turn


@dataclass
class _Composed:
    text: str
    mode: str


def main() -> int:
    spoken: list[tuple[str, str]] = []

    # 1. A real message routes through compose + speak.
    r = run_turn(
        user_id="smoke",
        transcribe=lambda: "Regis, how am I doing after this long stretch of work",
        compose=lambda **k: _Composed("Steady. You've earned a pause.", "companion"),
        speak_fn=lambda text, *, mode: spoken.append((text, mode)),
    )
    assert r.spoken and r.mode == "companion", r
    assert spoken == [("Steady. You've earned a pause.", "companion")], spoken

    # 2. A dismiss command short-circuits.
    r2 = run_turn(
        user_id="smoke",
        transcribe=lambda: "stop",
        compose=lambda **k: _Composed("should-not-compose", "companion"),
        speak_fn=lambda text, *, mode: spoken.append((text, mode)),
    )
    assert not r2.spoken and r2.intent == "dismiss", r2
    assert len(spoken) == 1, "dismiss must not speak"

    print("OK — voice loop smoke passed (message routed, dismiss short-circuited).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the smoke test**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
python -m voice.smoke_test
```
Expected: `OK — voice loop smoke passed (message routed, dismiss short-circuited).`

- [ ] **Step 4: Manual no-mic end-to-end (live LLM + TTS, real composer) — dev Mac only**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
python -m voice.cli --once --text "Regis, how am I right now?"
```
Expected: prints the transcript/intent/mode and `Regis: <reply>`, and the reply is spoken aloud via `say`. Confirms the real composer→TTS path. (Requires ChatGPT auth + DB.)

- [ ] **Step 5: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/voice/cli.py apps/voice/smoke_test.py
git commit -m "feat(voice): cli (--once/--text) + hardware-free loop smoke test"
```

---

## Task 9: Train the "Hey Regis" custom wake-word model (manual / out-of-band)

**Files:**
- Add (binary, gitignored or committed per size): `apps/inference/wake_word/models/hey_regis.onnx`

> This is a manual training step, not a code task — follow `apps/inference/wake_word/training/README.md`. It does NOT block the rest of Week 2: the loop runs on the built-in `hey_jarvis` placeholder until the model exists.

- [ ] **Step 1: Train via the official openWakeWord Colab (Path A in the README)**

Open the Colab in `apps/inference/wake_word/training/README.md`, set `target_word = "hey regis"`, Run All (~30-60 min on a free T4), download `hey_regis.onnx`.

- [ ] **Step 2: Drop the model into place**

```bash
cp ~/Downloads/hey_regis.onnx \
   "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference/wake_word/models/hey_regis.onnx"
```

- [ ] **Step 3: Verify the detector loads the custom model**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
DAYBOOK_WAKE_WORD=hey_regis python -c "from wake_word import VoiceWakeWordDetector; d=VoiceWakeWordDetector(wake_word='hey_regis'); d.get_model(); print('hey_regis model loaded')"
```
Expected: `hey_regis model loaded` (logs `[custom .onnx]`).

- [ ] **Step 4: Live mic test + commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
DAYBOOK_WAKE_WORD=hey_regis python -m voice.cli      # say "Hey Regis" → loop should trigger
```
Then decide commit vs gitignore by file size:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
ls -lh apps/inference/wake_word/models/hey_regis.onnx
# If small (a few MB), commit it:
git add apps/inference/wake_word/models/hey_regis.onnx
git commit -m "feat(voice): custom 'Hey Regis' wake-word model"
# If large, add to .gitignore instead and document the training step in STATUS.md.
```

---

## Task 10: Docs + integration smoke + tag

**Files:**
- Modify: `docs/ARCHITECTURE.md`, `docs/STATUS.md`

- [ ] **Step 1: Update ARCHITECTURE.md**

Add a short note under the relevant L5/L6 section (and the commitment-list lineage if a new commitment emerged) recording: the composer is the conversational turn engine; `apps/voice/loop.py` is the cross-layer waking-empath runtime (L1 wake/STT → L5 compose → L6 TTS); the composer reads the freshness-gated `BeliefState` (commitment #14) before composing.

- [ ] **Step 2: Update STATUS.md**

Date the entry `2026-05-28`. Record: Week 2 voice loop shipped — audio/STT/wake re-pulled, `fusion.loader.load_belief_state`, composer freshness-gated + real `gather_substrate`, `apps/voice/` runtime; note whether the custom `hey_regis.onnx` is trained yet.

- [ ] **Step 3: Full suite + integration smokes on the branch**

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
python -m pytest fusion/ features/ -q
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
python -m pytest wisp/ voice/ -q
python -m voice.smoke_test
python -m wisp.smoke_test
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps/inference"
python -m fusion.smoke_test
```
Expected: all green.

- [ ] **Step 4: Commit docs**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add docs/ARCHITECTURE.md docs/STATUS.md
git commit -m "docs: Week 2 voice loop — ARCHITECTURE + STATUS"
```

- [ ] **Step 5: Run the theory-aligner (standing rule: after implementation, before deploy)**

Dispatch the `theory-aligner` agent against the Week 2 branch. Verify the voice loop + composer rewiring align with commitments #3 (Wisp-as-interface), #5 (dual-mode), #14 (meta-context biases every layer). Apply any blocker/should-fix findings (own verification, own commits) before tagging.

- [ ] **Step 6: Open PR, merge, tag**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git push -u origin feat/week-2-voice-loop
gh pr create --title "Week 2 — state-aware voice loop" --body "Wake-word -> STT -> compose_utterance() -> TTS, composer reading freshness-gated BeliefState. Realigned to post-scrap reality (composer as turn engine, apps/voice/ runtime)."
# after merge:
git checkout main && git pull
git tag -a mvp-week-2-end -m "Week 2: state-aware voice loop"
git push origin mvp-week-2-end
```

---

## Notes / known follow-ups (log, don't silently absorb)

- **Freshness tuning:** `AxisEstimate.fresh_for_seconds` defaults may gate out Apple-Health-derived axes (hours old) for the waking-empath read. That's correct per #14, but per-axis `fresh_for_seconds` will likely need tuning once mac_sensors writes `meta_context` every 30s. Out of scope for Week 2; revisit in Week 3.
- **`wake_word/handlers.py` deferred:** command-side actions (LISTEN/SEE → DB via `gesture.recorder`) return when the gesture layer is rebuilt. Week 2 only routes DISMISS/SCRATCH_THAT inline.
- **kokoro TTS:** ships disabled (no model). To enable later: install `kokoro-onnx`, drop the model files where `kokoro_tts._model_dir()` expects, set `DAYBOOK_TTS=kokoro`.
- **Streaming TTS:** `run_turn` uses blocking `speak()`. Switching to `speak_streaming()` (lower first-audio latency) is a drop-in later change isolated to `_default_speak`.
