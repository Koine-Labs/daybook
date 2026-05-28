# Daybook MVP Week 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the per-axis-row schema (migration 0009), bring live writers online for Apple Health + Mac sensors, and light the first two L3 axes (`meta_context`, `sleep_stage`) — producing a runnable BeliefState end-to-end smoke test.

**Architecture:** Schema migration first, then sensor capture writers (one per modality) writing to `sensor_readings`, then a thin L3 fusion module reading from `sensor_readings` and producing per-axis rows in the reshaped `user_state_estimate`. No L4 prediction, no L5 decision, no audio/EEG in this week.

**Tech Stack:** Python 3.11 + psycopg + pandas + xgboost (already in venv), Neon Postgres (PG 17 + pgvector), Apple Health XML export, macOS AppleScript via `osascript` subprocess.

**Spec reference:** `docs/superpowers/specs/2026-05-27-vertical-slice-waking-empath-design.md` (sections 6, 7, 8 Week 1)

---

## Pre-flight context for the engineer

- Working tree is clean as of commit `8dc20ab`. Branch: `main`. Pushed to origin.
- All Python work runs from `apps/` with `inference/.venv` activated:
  ```bash
  cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
  source inference/.venv/bin/activate
  ```
- DB connection helper: `from db import get_conn` (after path bootstrap to `apps/inference/`).
- Default user: `DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"` (Aakash, only user).
- All timestamps are tz-aware UTC. Never strip timezone.
- Neon migrations are applied via psycopg from Python (the connection string has special chars that break `psql` arg parsing).
- For the schema migration (Tasks 2-4), use the Neon MCP tools (`mcp__Neon__prepare_database_migration` + `complete_database_migration`) which create a temp branch, let you verify, then promote to main.
- **Workflow: PR-per-task-cluster (8 PRs total).** Each PR groups 1-3 tasks by topical cohesion and dependency. See "PR structure" + "Worktree workflow" sections below. PR titles match the cards on the **Daybook MVP** GitHub Project board.

## File structure for Week 1

**Created this week:**
```
apps/inference/migrations/0009_per_axis_state_and_prediction_log.sql
apps/inference/capture/__init__.py
apps/inference/capture/mac_sensors.py
apps/inference/features/__init__.py
apps/inference/features/snapshot.py
apps/inference/fusion/__init__.py
apps/inference/fusion/belief_state.py
apps/inference/fusion/writer.py
apps/inference/fusion/smoke_test.py
apps/inference/fusion/axes/__init__.py
apps/inference/fusion/axes/meta_context.py
apps/inference/fusion/axes/sleep_stage.py
bin/sync_hk_export.py
```

**Modified this week:**
```
apps/inference/requirements.txt        (+ python-multipart)
docs/STATUS.md                         (week-1 status block)
docs/REBUILD_PLAN.md                   (week-1 checked off)
```

**Untouched this week (kept for later weeks or owned elsewhere):**
- `apps/pi/*` — separate Pi chat owns
- `apps/inference/audio/` — Week 2 (re-pull from v0 tag)
- `apps/inference/{prediction,decision,retrieval}/` — Week 4
- `apps/inference/capture/{watch,eeg,mic_wakeword,mic_continuous}.py` — later weeks (Week 1's watch path is the standalone `bin/sync_hk_export.py`)

---

## PR structure (8 PRs, parallel-friendly)

Every task in this plan lives inside exactly one PR. PRs cluster tasks by topical cohesion and dependency. The Daybook MVP GitHub Project board has one card per PR.

| PR | Title | Tasks | Branch | Depends on |
|---|---|---|---|---|
| **#1** | Preflight: python-multipart + FeatureSnapshot | 1, 5 | `mvp/week-1/pr1-preflight` | — |
| **#2** | Migration 0009: per-axis-row state + prediction_log + consent | 2, 3, 4 | `mvp/week-1/migration-0009` | — |
| **#3** | Apple Health sync (`bin/sync_hk_export.py`) | 6 | `mvp/week-1/pr3-apple-health-sync` | #2 (writes to sensor_readings) |
| **#4** | Mac sensors capture (`capture/mac_sensors.py`) | 7 | `mvp/week-1/pr4-mac-sensors` | #1 (FeatureSnapshot), #2 (sensor_readings shape) |
| **#5** | Fusion primitives (BeliefState + writer) | 8 | `mvp/week-1/pr5-fusion-primitives` | #2 (user_state_estimate shape) |
| **#6** | meta_context axis | 9 | `mvp/week-1/pr6-meta-context-axis` | #4 (mac_activity data), #5 (AxisEstimate) |
| **#7** | sleep_stage axis | 10 | `mvp/week-1/pr7-sleep-stage-axis` | #3 (apple_health_sleep_stage data), #5 (AxisEstimate) |
| **#8** | End-to-end smoke + Week-1 closeout | 11, 12 | `mvp/week-1/pr8-smoke-closeout` | #6, #7 |

### Dependency graph + parallel waves

```
Wave 1 (concurrent):   #1 ──┐
                       #2 ──┼── all three can start at the same time
                       (#3 needs #2 merged before it can start running its smoke;
                        the code for #3 can be written in parallel)

Wave 2 (after #1, #2): #4 (depends on #1, #2)
                       #5 (depends on #2)
                       — these two can run concurrent with each other

Wave 3 (after #4, #5): #6 (depends on #4, #5)
                       #7 (depends on #3, #5)
                       — these two can run concurrent with each other

Wave 4 (after #6, #7): #8
```

With 2-3 worktrees + 2-3 Claude sessions, you can realistically compress Week 1 from ~5-6 days to ~3 days. Without parallelism, work the PRs in dependency order: #1 → #2 → #3 → #4 → #5 → #6 → #7 → #8.

---

## Worktree workflow (one worktree per active PR branch)

To work multiple PRs in parallel without git tripping over itself, use git worktrees. Convention:

```bash
# Root repo stays at /Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook (main branch).
# Each worktree lives under ~/Code/daybook-worktrees/<branch-slug>/

mkdir -p ~/Code/daybook-worktrees

# Example: spin up worktree for PR #1
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git worktree add ~/Code/daybook-worktrees/pr1-preflight -b mvp/week-1/pr1-preflight main

# Then work in that worktree:
cd ~/Code/daybook-worktrees/pr1-preflight
# ...do the task work...
git push -u origin mvp/week-1/pr1-preflight
gh pr create --title "PR #1 — Preflight: python-multipart + FeatureSnapshot" --body "$(cat <<EOF
Closes PR #1 card on Daybook MVP board.
Implements Tasks 1 (python-multipart) + 5 (FeatureSnapshot).

## Test plan
- [x] python-multipart installs cleanly; FastAPI bridge starts
- [x] features/test_snapshot.py: 3 tests passing

Spec: docs/superpowers/specs/2026-05-27-vertical-slice-waking-empath-design.md
Plan: docs/superpowers/plans/2026-05-27-mvp-week-1-schema-watch-mac-sensors.md
EOF
)"

# After PR merges, clean up the worktree:
gh pr merge <pr-number> --squash --delete-branch
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git pull
git worktree remove ~/Code/daybook-worktrees/pr1-preflight
```

The repo also has a `superpowers:using-git-worktrees` skill if you want a more guided setup.

### PR commit + close-out checklist (every PR)

Each PR ends with the same 4 steps:

1. `git push -u origin <branch>`
2. `gh pr create --title "<PR # — title>" --body "<body referencing spec + plan + tasks closed + test plan>"`
3. Self-review the diff in the GitHub UI (read each file, check it does what you intended)
4. `gh pr merge <pr-number> --squash --delete-branch`
5. Move the Project board card to **Done**

Per-task "Step N: Commit" blocks inside each Task below stay the same — they're commits *within* the PR branch. The PR's create/merge happen at the end of the last task in the cluster.

---

## Task 1: Unblock FastAPI bridge — add python-multipart

**PR:** #1 (Preflight). Cluster with Task 5.

**Files:**
- Modify: `apps/inference/requirements.txt`
- Verify: `apps/api/app.py` (no edit — just import test)

**Why:** Pre-existing finding from the cleanup commit. `apps/api/routes/recall.py` uses `UploadFile` from FastAPI, which requires `python-multipart`. The bridge can't start without it. One-line fix to unblock all downstream API work.

- [ ] **Step 1: Check that python-multipart isn't already in requirements**

Run: `grep -i multipart apps/inference/requirements.txt`
Expected: no output (not present).

- [ ] **Step 2: Append python-multipart to requirements**

Modify `apps/inference/requirements.txt` — add to the dependencies block:
```
python-multipart>=0.0.9
```

- [ ] **Step 3: Install into venv**

Run:
```bash
cd apps && source inference/.venv/bin/activate
pip install "python-multipart>=0.0.9"
```
Expected: `Successfully installed python-multipart-...`

- [ ] **Step 4: Smoke-test the bridge starts**

Run:
```bash
cd apps/api && python -c "from app import app; print('OK:', app.title)"
```
Expected: `OK: Daybook API`

- [ ] **Step 5: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/inference/requirements.txt
git commit -m "$(cat <<'EOF'
fix: add python-multipart to requirements

apps/api/routes/recall.py uses FastAPI UploadFile, which requires
python-multipart. The bridge can't start without it. Pre-existing
gap surfaced in the cleanup audit; one-line fix.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Write migration 0009 SQL — per-axis-row reshape + prediction_log + consent columns

**PR:** #2 (Migration 0009). Tasks 2, 3, 4 all live in this PR.

**Files:**
- Create: `apps/inference/migrations/0009_per_axis_state_and_prediction_log.sql`

**Why:** The whole L3 architecture (BeliefState, freshness policy, per-axis predictors) depends on per-axis-row storage. Current schema is wide-row from migration 0002. This is the structural change everything else builds on.

**Branch:** Create feature branch first.

- [ ] **Step 1: Create feature branch**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git checkout -b mvp/week-1/migration-0009
```

- [ ] **Step 2: Write the migration SQL**

Create `apps/inference/migrations/0009_per_axis_state_and_prediction_log.sql`:

```sql
-- 0009_per_axis_state_and_prediction_log.sql
-- Reshape user_state_estimate (wide-row → per-axis-row), add prediction_log,
-- add consent metadata columns on sensor_readings.
--
-- Aligned to ARCHITECTURE.md §3 L3 (per-axis storage with freshness policy)
-- and commitment #13 (outcome-driven action selection).
--
-- Backfill: existing user_state_estimate rows (sleep classifier output) are
-- migrated to per-axis-rows in the same transaction. One wide row in →
-- up to N per-axis rows out (one per non-NULL axis).

BEGIN;

-- =============================================================================
-- 1. user_state_estimate v2 — per-axis-row
-- =============================================================================

CREATE TABLE user_state_estimate_v2 (
  id            UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id       UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  axis          TEXT         NOT NULL,                -- 'arousal_inferred', 'meta_context', 'sleep_stage', 'state_declared', 'audio_social_context', 'cognitive_load'
  timestamp     TIMESTAMPTZ  NOT NULL,
  value         JSONB        NOT NULL,                -- {"category": "focused"} or {"scalar": 0.55} or {"label": "REM", "prob": 0.71}
  confidence    DOUBLE PRECISION CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  source        TEXT,                                 -- 'L3.fusion.meta_context', 'classifier.binary_rem', etc.
  meta_context  TEXT,                                 -- 'waking', 'sleep', or sub-context like 'waking/focused' — denormalized for fast filter
  i_model_id    UUID,                                 -- commitment #1
  session_id    UUID         REFERENCES sleep_sessions(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_use_v2_user_axis_ts ON user_state_estimate_v2(user_id, axis, timestamp DESC);
CREATE INDEX idx_use_v2_user_ts_meta ON user_state_estimate_v2(user_id, timestamp DESC) WHERE meta_context IS NOT NULL;

-- Backfill from existing wide-row user_state_estimate.
-- One row in → multiple per-axis rows out for each non-NULL column.

-- sleep_stage axis (from stage_proba)
INSERT INTO user_state_estimate_v2 (user_id, axis, timestamp, value, confidence, source, session_id)
SELECT
  user_id,
  'sleep_stage',
  estimated_at,
  stage_proba,
  confidence,
  source,
  session_id
FROM user_state_estimate
WHERE stage_proba IS NOT NULL;

-- arousal_inferred axis (from arousal scalar)
INSERT INTO user_state_estimate_v2 (user_id, axis, timestamp, value, confidence, source, session_id)
SELECT
  user_id,
  'arousal_inferred',
  estimated_at,
  jsonb_build_object('scalar', arousal),
  confidence,
  source,
  session_id
FROM user_state_estimate
WHERE arousal IS NOT NULL;

-- valence axis (from valence scalar) — kept for backward-compat even though
-- v1 L3 doesn't fuse it yet. We can extend later without touching schema.
INSERT INTO user_state_estimate_v2 (user_id, axis, timestamp, value, confidence, source, session_id)
SELECT
  user_id,
  'valence_inferred',
  estimated_at,
  jsonb_build_object('scalar', valence),
  confidence,
  source,
  session_id
FROM user_state_estimate
WHERE valence IS NOT NULL;

-- presence axis (from presence scalar) — same rationale
INSERT INTO user_state_estimate_v2 (user_id, axis, timestamp, value, confidence, source, session_id)
SELECT
  user_id,
  'presence_inferred',
  estimated_at,
  jsonb_build_object('scalar', presence),
  confidence,
  source,
  session_id
FROM user_state_estimate
WHERE presence IS NOT NULL;

-- Drop wide-row table; rename v2 into place.
DROP TABLE user_state_estimate;
ALTER TABLE user_state_estimate_v2 RENAME TO user_state_estimate;
ALTER INDEX idx_use_v2_user_axis_ts RENAME TO idx_use_user_axis_ts;
ALTER INDEX idx_use_v2_user_ts_meta RENAME TO idx_use_user_ts_meta;

-- =============================================================================
-- 2. prediction_log — every Regis discrete-action choice for #13 outcome-driven learning
-- =============================================================================

CREATE TABLE prediction_log (
  id                     UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id                UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ts                     TIMESTAMPTZ  NOT NULL,
  action_type            TEXT         NOT NULL,           -- 'interject', 'no_interject', 'chat_response'
  action_kind            TEXT,                            -- 'witness', 'companion', 'check_in', 'capture_ack', etc.
  state_before           JSONB        NOT NULL,           -- snapshot of relevant axes at decision time
  expected_state_after   JSONB,                           -- L4 predictor's forecast (naive in v1)
  observed_state_after   JSONB,                           -- filled by reconciler 5-15min later
  user_response_label    TEXT         CHECK (user_response_label IS NULL OR user_response_label IN ('accepted','rejected','ignored','unknown')),
  user_response_signal   JSONB,                           -- raw signal (next-utterance prosody, HR delta, etc.)
  i_model_id             UUID,                            -- commitment #1
  created_at             TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_prediction_log_user_ts ON prediction_log(user_id, ts DESC);
CREATE INDEX idx_prediction_log_user_action_ts ON prediction_log(user_id, action_type, ts DESC);

-- =============================================================================
-- 3. sensor_readings consent metadata columns
-- =============================================================================

ALTER TABLE sensor_readings
  ADD COLUMN consent_scope  TEXT,         -- 'mic_continuous_v1', 'cam_continuous_v1', etc. — indexes consent record at write time
  ADD COLUMN suppressed_for JSONB;        -- {"reason": "other_voice_present", "window_start": "..."} — when pipeline paused but row still landed

CREATE INDEX idx_sensor_readings_consent_scope ON sensor_readings(consent_scope) WHERE consent_scope IS NOT NULL;

COMMIT;
```

- [ ] **Step 3: Verify SQL syntax with psycopg parse (no DB roundtrip)**

Run:
```bash
cd apps/inference && python -c "
from pathlib import Path
sql = Path('migrations/0009_per_axis_state_and_prediction_log.sql').read_text()
print(f'OK: {len(sql)} chars, {sql.count(chr(10))+1} lines, {sql.count(\";\")} statements')
"
```
Expected: `OK: ~5000 chars, ~150 lines, ~15 statements`

- [ ] **Step 4: Commit migration to branch**

```bash
git add apps/inference/migrations/0009_per_axis_state_and_prediction_log.sql
git commit -m "$(cat <<'EOF'
migration: 0009 — per-axis-row state + prediction_log + consent metadata

Reshape user_state_estimate from wide-row to per-axis-row per
ARCHITECTURE.md §3 L3. Add prediction_log for commitment #13 outcome-
driven action selection. Add consent metadata columns on sensor_readings
for commitment #8 + privacy policy #1.

Backfill: existing wide-row rows fan out to per-axis-rows (sleep_stage,
arousal_inferred, valence_inferred, presence_inferred). One transaction,
deferred constraint check via DROP+RENAME pattern.

Branch v0-pre-rebuild + Neon branch pre-rebuild-snapshot are the recovery
path if backfill misbehaves.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Apply migration 0009 to a Neon temp branch, verify backfill correctness

**PR:** #2 (Migration 0009). Verification step inside the PR — no commit, just Neon-side verification.

**Files:**
- No code changes (verification only)

**Why:** Schema reshape with backfill is risky. Apply to a temp branch first, run row-count checks, then promote.

- [ ] **Step 1: Capture pre-migration state from main**

Run via Neon MCP (use `mcp__Neon__run_sql` against the main `production` branch):
```sql
-- Row counts to verify the backfill
SELECT
  count(*) FILTER (WHERE stage_proba IS NOT NULL) AS n_with_stage_proba,
  count(*) FILTER (WHERE arousal IS NOT NULL) AS n_with_arousal,
  count(*) FILTER (WHERE valence IS NOT NULL) AS n_with_valence,
  count(*) FILTER (WHERE presence IS NOT NULL) AS n_with_presence,
  count(*) AS total_rows
FROM user_state_estimate;
```
Record the numbers — call these `N_stage`, `N_arousal`, `N_valence`, `N_presence`, `N_total`.

- [ ] **Step 2: Prepare migration on a temp Neon branch**

Use `mcp__Neon__prepare_database_migration` with:
- `migrationSql`: contents of `apps/inference/migrations/0009_per_axis_state_and_prediction_log.sql`
- The tool creates a temp branch and applies the migration. It returns a `migrationId` and `branch.id`.

- [ ] **Step 3: Verify schema on temp branch**

Use `mcp__Neon__run_sql` against the temp branch:
```sql
-- Verify new table shape
\d user_state_estimate;
-- (or for MCP, use:)
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'user_state_estimate'
ORDER BY ordinal_position;
```

Expected columns: `id, user_id, axis, timestamp, value, confidence, source, meta_context, i_model_id, session_id, created_at`. NO `stage_proba`, `arousal`, `valence`, `presence`, `features`.

- [ ] **Step 4: Verify backfill row counts on temp branch**

```sql
SELECT axis, count(*) FROM user_state_estimate GROUP BY axis ORDER BY axis;
```

Expected: counts match `N_stage` (sleep_stage), `N_arousal` (arousal_inferred), `N_valence` (valence_inferred), `N_presence` (presence_inferred). Total rows ≈ sum of those (one wide row → multiple per-axis rows).

- [ ] **Step 5: Verify prediction_log + sensor_readings consent columns exist on temp branch**

```sql
SELECT column_name FROM information_schema.columns WHERE table_name = 'prediction_log';
SELECT column_name FROM information_schema.columns
  WHERE table_name = 'sensor_readings' AND column_name IN ('consent_scope','suppressed_for');
```
Expected: prediction_log has 11 columns; sensor_readings has both new columns.

- [ ] **Step 6: Sample one backfilled row to verify shape**

```sql
SELECT axis, value, source, confidence
FROM user_state_estimate
WHERE axis = 'sleep_stage'
ORDER BY timestamp DESC
LIMIT 1;
```
Expected: a row where `value` is a JSONB stage_proba dict (e.g., `{"REM": 0.71}`), `source` matches one of the v0 source labels (`'realtime_v1'`, etc.).

- [ ] **Step 7: If all verifications pass, do NOT promote yet — wait for Task 4**

The temp branch is now ready. Note the `migrationId` for the next task.

---

## Task 4: Promote migration to main Neon branch + open PR

**PR:** #2 (Migration 0009). **Final task in this PR** — promote to Neon main, push branch, open PR, self-review, merge.

**Files:**
- No code changes (verification only) — but this is where the migration goes live

**Why:** Separate "apply to temp" from "promote to main" gives a safe checkpoint before the irreversible step.

- [ ] **Step 1: Promote the migration via Neon MCP**

Use `mcp__Neon__complete_database_migration` with the `migrationId` from Task 3 Step 2.

The tool promotes the temp branch's state to the main branch and cleans up the temp branch.

- [ ] **Step 2: Verify on main branch**

Re-run the queries from Task 3 Steps 3-6 against the `production` branch this time. Same expected results.

- [ ] **Step 3: Push branch + open PR**

```bash
git push -u origin mvp/week-1/migration-0009
gh pr create --title "Migration 0009: per-axis-row state + prediction_log + consent metadata" --body "$(cat <<'EOF'
## Summary
- Reshape `user_state_estimate` from wide-row to per-axis-row (ARCHITECTURE.md §3 L3)
- Add `prediction_log` table for commitment #13 (outcome-driven action selection)
- Add `consent_scope` + `suppressed_for` columns to `sensor_readings` (commitment #8 + privacy policy #1)

## Applied
- Migration applied to production Neon branch via Neon MCP (verified on temp branch first).
- Backfill verified: wide-row rows fanned to per-axis-rows; counts match per-axis breakdown.

## Test plan
- [x] Schema verified on temp branch (information_schema.columns)
- [x] Backfill row counts match per-axis breakdown
- [x] Sample row inspected — JSONB value shape correct
- [x] prediction_log + sensor_readings consent columns present
- [ ] Downstream sensor capture + fusion smoke tests (Tasks 5-11)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Merge PR after self-review**

```bash
gh pr merge --squash --delete-branch
git checkout main
git pull
```

Verify `main` is now ahead with the migration commit.

---

## Task 5: Create FeatureSnapshot envelope dataclass

**PR:** #1 (Preflight). Cluster with Task 1. **Final task in PR #1** — open + merge PR at end of this task.

**Files:**
- Create: `apps/inference/features/__init__.py`
- Create: `apps/inference/features/snapshot.py`
- Create: `apps/inference/features/test_snapshot.py`

**Why:** Per ARCHITECTURE.md §3 L2, FeatureSnapshot is the uniform envelope every L2 feature extractor produces. Locking the shape now means downstream fusion + prediction don't have to handle inconsistent inputs.

- [ ] **Step 1: Create `apps/inference/features/__init__.py`**

```python
"""L2 feature layer — per-modality feature extractors producing FeatureSnapshots."""
from __future__ import annotations

from .snapshot import FeatureSnapshot

__all__ = ["FeatureSnapshot"]
```

- [ ] **Step 2: Write the failing test**

Create `apps/inference/features/test_snapshot.py`:

```python
"""Tests for FeatureSnapshot envelope."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from features.snapshot import FeatureSnapshot


def test_basic_construction():
    snap = FeatureSnapshot(
        user_id="61c18d4c-1c20-408a-bd5f-f5f88fd9922f",
        timestamp=datetime(2026, 5, 27, 15, 0, tzinfo=timezone.utc),
        modality="biometric",
        source="watch.hr_30s",
        payload={"hr_mean": 68.2, "hr_std": 3.1},
    )
    assert snap.modality == "biometric"
    assert snap.payload["hr_mean"] == pytest.approx(68.2)
    assert snap.confidence is None
    assert snap.meta_context_hint is None


def test_to_dict_roundtrip():
    snap = FeatureSnapshot(
        user_id="61c18d4c-1c20-408a-bd5f-f5f88fd9922f",
        timestamp=datetime(2026, 5, 27, 15, 0, tzinfo=timezone.utc),
        modality="mac",
        source="mac.app_activity",
        payload={"active_app": "Cursor", "keystrokes_per_min": 42},
        confidence=0.9,
        meta_context_hint="waking",
    )
    d = snap.to_dict()
    assert d["modality"] == "mac"
    assert d["confidence"] == 0.9
    assert d["meta_context_hint"] == "waking"
    assert d["timestamp"].endswith("+00:00")  # tz-aware ISO


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError, match="tz-aware"):
        FeatureSnapshot(
            user_id="61c18d4c-1c20-408a-bd5f-f5f88fd9922f",
            timestamp=datetime(2026, 5, 27, 15, 0),  # naive — should raise
            modality="biometric",
            source="watch.hr_30s",
            payload={},
        )
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd apps && source inference/.venv/bin/activate
cd inference && python -m pytest features/test_snapshot.py -v
```
Expected: `FAILED` with `ModuleNotFoundError: No module named 'features.snapshot'`.

- [ ] **Step 4: Write the implementation**

Create `apps/inference/features/snapshot.py`:

```python
"""FeatureSnapshot — uniform envelope produced by every L2 feature extractor.

Per ARCHITECTURE.md §3 L2: every modality's L2 output is a FeatureSnapshot
with a uniform envelope (timestamp, source, modality, confidence) and a
modality-specific payload (JSONB-shaped dict).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FeatureSnapshot:
    """One L2 feature-extraction output, ready for L3 fusion."""

    user_id: str
    timestamp: datetime               # tz-aware UTC
    modality: str                     # 'biometric' | 'audio' | 'mac' | 'eeg' | 'cam' | 'derived'
    source: str                       # e.g., 'watch.hr_30s', 'mac.app_activity'
    payload: dict[str, Any]           # modality-specific feature dict
    confidence: float | None = None   # [0, 1] if computable
    duration_ms: int | None = None    # observation window length
    meta_context_hint: str | None = None  # e.g., 'waking' if known at L2
    i_model_id: str | None = None     # commitment #1

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("FeatureSnapshot.timestamp must be tz-aware UTC")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")

    def to_dict(self) -> dict[str, Any]:
        """Serializable dict (timestamp → ISO string)."""
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd apps/inference && python -m pytest features/test_snapshot.py -v
```
Expected: `3 passed`.

- [ ] **Step 6: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/inference/features/__init__.py apps/inference/features/snapshot.py apps/inference/features/test_snapshot.py
git commit -m "$(cat <<'EOF'
feat(L2): FeatureSnapshot envelope dataclass

Uniform envelope every L2 feature extractor produces. Per ARCHITECTURE.md
§3 L2: timestamp + source + modality + confidence + payload. Enforces
tz-aware timestamps and [0,1] confidence range.

3 tests passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Apple Health incremental sync script — `bin/sync_hk_export.py`

**PR:** #3 (Apple Health sync). Single task = single PR. Branch off PR #2 once merged.

**Files:**
- Create: `bin/sync_hk_export.py`
- Verify against: latest Apple Health `export.xml` (Aakash's iCloud Drive)

**Why:** Without iOS, the only way live watch data reaches Daybook is the manual Apple Health XML export. The existing `apps/inference/parse_apple_health.py` was a one-shot loader (already run for the 10yr history). This script is the *incremental, idempotent* sync — designed to run on a cron or be invoked manually after each export — that brings in just the new data since the last sync, and writes sleep stages + HR records as `sensor_readings`.

**Key design decisions:**
- Writes to `sensor_readings` (not a custom table). Uses two `kind` discriminators: `apple_health_sleep_stage` and `apple_health_hr`. Payload is the structured packet per the polymorphic content commitment (#2).
- Tracks the last-synced cutoff in `~/.daybook/sync_state.json` so re-running is fast and idempotent.
- Streaming XML parse (the export file is multi-GB for long histories) — never load the whole tree into memory.

- [ ] **Step 1: Inspect what's currently loaded from Apple Health (read-only)**

Run via Neon MCP (against `production` branch):
```sql
SELECT kind, count(*), min(recorded_at), max(recorded_at)
FROM sensor_readings
WHERE kind LIKE 'apple_health%' OR kind IN ('sleep_stage', 'hr', 'hrv')
GROUP BY kind
ORDER BY kind;
```

**Schema reminder:** `sensor_readings` (per migration 0001) has columns `(id, user_id, source, kind, recorded_at, payload)` — the timestamp column is `recorded_at`, NOT `timestamp`, and `source` is a NOT NULL row-level column (not part of payload). Migration 0009 added `consent_scope` + `suppressed_for`. All sensor_readings INSERT and SELECT in this plan should use these column names.
Record what's there. This tells us whether `parse_apple_health.py` used the `apple_health_*` naming convention or something else.

- [ ] **Step 2: Read parse_apple_health.py to understand its naming + insertion logic**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
head -80 apps/inference/parse_apple_health.py
```
Note: which table it writes to, what `kind` values it uses for sleep stages and HR, what it sets as `timestamp`. The new sync script will use the same conventions to stay compatible.

- [ ] **Step 3: Write the sync script**

Create `bin/sync_hk_export.py`:

```python
#!/usr/bin/env python3
"""Incremental Apple Health XML export sync into sensor_readings.

Reads an Apple Health export XML (typically ~/Library/Mobile Documents/... or
~/Downloads/export.xml) and inserts only records newer than the last sync
cutoff. Writes sleep stages and HR (extend later for HRV, SpO2, resp).

Usage:
    bin/sync_hk_export.py /path/to/export.xml
    bin/sync_hk_export.py /path/to/export.xml --since 2026-05-20
    bin/sync_hk_export.py /path/to/export.xml --dry-run

State file: ~/.daybook/sync_state.json
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# Path bootstrap so we can `from db import get_conn`.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "inference"))

from db import get_conn  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"
STATE_PATH = Path.home() / ".daybook" / "sync_state.json"

# HealthKit type identifiers we care about for Week 1.
# Extend later for HRV (HKQuantityTypeIdentifierHeartRateVariabilitySDNN),
# SpO2, respiratory rate, etc.
TYPE_HR = "HKQuantityTypeIdentifierHeartRate"
TYPE_SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"

# Apple sleep category values → our internal labels.
SLEEP_STAGE_MAP = {
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
    "HKCategoryValueSleepAnalysisAsleep": "asleep_legacy",
    "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep",
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
}


def load_state() -> dict[str, str]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def save_state(state: dict[str, str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def parse_hk_datetime(s: str) -> datetime:
    """Apple Health timestamps look like '2026-05-25 23:14:33 -0700'."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z").astimezone(timezone.utc)


def iter_records(xml_path: Path):
    """Stream-iterate <Record> elements without loading the whole tree."""
    for event, elem in ET.iterparse(str(xml_path), events=("end",)):
        if elem.tag == "Record":
            yield elem.attrib
            elem.clear()


def sync(
    *,
    xml_path: Path,
    since: datetime | None = None,
    user_id: str = DEFAULT_USER_ID,
    dry_run: bool = False,
) -> dict[str, int]:
    state = load_state()
    state_key = f"{user_id}:last_synced_at"
    cutoff: datetime | None = since
    if cutoff is None and state_key in state:
        cutoff = datetime.fromisoformat(state[state_key])

    print(f"Sync starting. cutoff={cutoff} dry_run={dry_run}", flush=True)

    new_rows: list[tuple] = []
    counters = {"hr": 0, "sleep": 0, "skipped_before_cutoff": 0, "skipped_other_type": 0}
    latest_ts_seen: datetime | None = None

    for rec in iter_records(xml_path):
        rec_type = rec.get("type")
        start = parse_hk_datetime(rec["startDate"])
        end = parse_hk_datetime(rec["endDate"]) if rec.get("endDate") else start

        if latest_ts_seen is None or end > latest_ts_seen:
            latest_ts_seen = end

        if cutoff and end <= cutoff:
            counters["skipped_before_cutoff"] += 1
            continue

        if rec_type == TYPE_HR:
            new_rows.append(
                (
                    user_id,
                    "apple_health_hr",
                    start,
                    json.dumps({"bpm": float(rec["value"]), "source": rec.get("sourceName", "")}),
                )
            )
            counters["hr"] += 1
        elif rec_type == TYPE_SLEEP:
            stage = SLEEP_STAGE_MAP.get(rec.get("value", ""), "unknown")
            new_rows.append(
                (
                    user_id,
                    "apple_health_sleep_stage",
                    start,
                    json.dumps({
                        "stage": stage,
                        "end": end.isoformat(),
                        "source": rec.get("sourceName", ""),
                        "duration_s": int((end - start).total_seconds()),
                    }),
                )
            )
            counters["sleep"] += 1
        else:
            counters["skipped_other_type"] += 1

    print(f"Parsed {len(new_rows)} new rows. Counters: {counters}", flush=True)

    if dry_run:
        print("Dry run — not inserting.", flush=True)
        return counters

    if not new_rows:
        print("Nothing to insert.", flush=True)
        return counters

    with get_conn() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO sensor_readings (user_id, kind, timestamp, payload)
            VALUES (%s, %s, %s, %s::jsonb)
            """,
            new_rows,
        )
        conn.commit()

    if latest_ts_seen is not None:
        state[state_key] = latest_ts_seen.isoformat()
        save_state(state)
        print(f"Cutoff advanced to {latest_ts_seen.isoformat()}", flush=True)

    return counters


def _cli() -> int:
    p = argparse.ArgumentParser(prog="sync_hk_export", description="Incremental Apple Health → sensor_readings sync.")
    p.add_argument("xml_path", type=Path, help="Path to Apple Health export.xml")
    p.add_argument("--since", type=str, default=None, help="ISO timestamp; only records strictly after this are imported.")
    p.add_argument("--user-id", type=str, default=DEFAULT_USER_ID)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not args.xml_path.exists():
        print(f"export.xml not found at {args.xml_path}", file=sys.stderr)
        return 1

    since = datetime.fromisoformat(args.since) if args.since else None
    counters = sync(xml_path=args.xml_path, since=since, user_id=args.user_id, dry_run=args.dry_run)
    print(f"DONE. {counters}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
```

- [ ] **Step 4: Make it executable**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
chmod +x bin/sync_hk_export.py
```

- [ ] **Step 5: Smoke-test with `--dry-run` against a tiny XML fixture**

Create a minimal fixture at `/tmp/hk_fixture.xml`:
```bash
cat > /tmp/hk_fixture.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
  <Record type="HKQuantityTypeIdentifierHeartRate"
          sourceName="Apple Watch"
          startDate="2026-05-26 15:00:00 -0700"
          endDate="2026-05-26 15:00:00 -0700"
          value="68"/>
  <Record type="HKQuantityTypeIdentifierHeartRate"
          sourceName="Apple Watch"
          startDate="2026-05-26 15:00:30 -0700"
          endDate="2026-05-26 15:00:30 -0700"
          value="72"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis"
          sourceName="Apple Watch"
          startDate="2026-05-27 02:30:00 -0700"
          endDate="2026-05-27 03:00:00 -0700"
          value="HKCategoryValueSleepAnalysisAsleepREM"/>
</HealthData>
EOF
```

Run:
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
source inference/.venv/bin/activate
python ../bin/sync_hk_export.py /tmp/hk_fixture.xml --dry-run
```

Expected output: `Parsed 3 new rows. Counters: {'hr': 2, 'sleep': 1, 'skipped_before_cutoff': 0, 'skipped_other_type': 0}` and `Dry run — not inserting.`

- [ ] **Step 6: Smoke-test for real against the fixture (inserts 3 rows)**

```bash
python ../bin/sync_hk_export.py /tmp/hk_fixture.xml
```

Expected: `DONE. {'hr': 2, 'sleep': 1, ...}` and the cutoff is advanced in `~/.daybook/sync_state.json`.

Verify the insert via Neon MCP:
```sql
SELECT kind, recorded_at, payload FROM sensor_readings
WHERE kind IN ('apple_health_hr','apple_health_sleep_stage')
  AND recorded_at >= '2026-05-26'
ORDER BY recorded_at DESC
LIMIT 5;
```
Expected: the 3 fixture rows appear.

- [ ] **Step 7: Test idempotency — re-run and confirm zero new inserts**

```bash
python ../bin/sync_hk_export.py /tmp/hk_fixture.xml
```
Expected: `Parsed 0 new rows. ... skipped_before_cutoff: 3 ...` and no DB writes.

- [ ] **Step 8: Clean up the fixture rows so smoke test doesn't pollute prod data**

Use Neon MCP:
```sql
DELETE FROM sensor_readings
WHERE kind IN ('apple_health_hr','apple_health_sleep_stage')
  AND payload->>'source' = 'Apple Watch'
  AND recorded_at BETWEEN '2026-05-26 21:00:00+00' AND '2026-05-27 11:00:00+00';
```
(Adjust the time window to exactly cover the fixture rows.)

Also reset the sync state:
```bash
rm -f ~/.daybook/sync_state.json
```

- [ ] **Step 9: Commit**

```bash
git add bin/sync_hk_export.py
git commit -m "$(cat <<'EOF'
feat(L1): bin/sync_hk_export.py — incremental Apple Health → sensor_readings

Streaming XML parser, idempotent, tracks last-synced cutoff in
~/.daybook/sync_state.json. Writes apple_health_hr + apple_health_sleep_stage
rows. Extend later for HRV / SpO2 / resp.

Smoke-tested against a 3-row fixture: dry-run + real insert + idempotency
+ cleanup all verified.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Mac sensors capture daemon — `apps/inference/capture/mac_sensors.py`

**PR:** #4 (Mac sensors capture). Single task = single PR. Depends on PR #1 (FeatureSnapshot) + PR #2 (sensor_readings shape) both merged.

**Files:**
- Create: `apps/inference/capture/__init__.py`
- Create: `apps/inference/capture/mac_sensors.py`
- Create: `apps/inference/capture/smoke_test.py`

**Why:** The Mac itself is the cheapest waking-context sensor available — knowing `active_app` + activity (or idleness) is enough to populate the `meta_context` axis (focused / context-switching / idle / etc.) without any new hardware. Runs in a daemon loop, writing every 30s.

**Design note — keystrokes vs idle_seconds:** The spec's Week 1 exit criteria mention "keystrokes_per_min". This plan instead uses `idle_seconds` (time since last HID event, via `ioreg`). Same signal, no accessibility permission gate, no `pynput` dependency. The `meta_context` classifier (Task 9) only needs an active-vs-idle distinction, which idle_seconds gives. Adding true keystroke-rate sensing is a clean Week-2+ extension if desired.

- [ ] **Step 1: Create `apps/inference/capture/__init__.py`**

```python
"""L1 capture layer — sensor writers producing sensor_readings rows."""
```

- [ ] **Step 2: Write the failing smoke test**

Create `apps/inference/capture/smoke_test.py`:

```python
"""Smoke test: capture one Mac sensor reading and verify the shape."""
from __future__ import annotations

import sys
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(INF_DIR))

from capture.mac_sensors import capture_once  # noqa: E402


def main() -> int:
    snap = capture_once()
    print(f"FeatureSnapshot: {snap.to_dict()}")
    assert snap.modality == "mac"
    assert "active_app" in snap.payload
    assert "idle_seconds" in snap.payload
    assert snap.timestamp.tzinfo is not None
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run smoke test to verify it fails**

```bash
cd apps/inference && python -m capture.smoke_test
```
Expected: `ModuleNotFoundError: No module named 'capture.mac_sensors'`.

- [ ] **Step 4: Write the implementation**

Create `apps/inference/capture/mac_sensors.py`:

```python
"""Mac-as-sensor: frontmost app, idle time, keystrokes-per-min.

Writes one sensor_readings row per tick. Cheapest waking-context sensor
available — no new hardware, no permissions beyond AppleScript.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402
from features.snapshot import FeatureSnapshot  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def _frontmost_app() -> str:
    """Return the frontmost (visible, active) app name."""
    script = 'tell application "System Events" to get name of first process whose frontmost is true'
    try:
        out = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return out.stdout.strip()
    except Exception as e:
        logger.warning("osascript frontmost failed: %s", e)
        return "unknown"


def _idle_seconds() -> float:
    """Return system idle time in seconds (time since last HID input)."""
    try:
        out = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        for line in out.stdout.splitlines():
            if "HIDIdleTime" in line:
                # line format: ... "HIDIdleTime" = 1234567890  (nanoseconds)
                ns = int(line.split("=")[1].strip())
                return ns / 1e9
    except Exception as e:
        logger.warning("ioreg idle time failed: %s", e)
    return -1.0


def capture_once(user_id: str = DEFAULT_USER_ID) -> FeatureSnapshot:
    """Capture one snapshot. Does NOT write to DB; caller writes."""
    now = datetime.now(timezone.utc)
    return FeatureSnapshot(
        user_id=user_id,
        timestamp=now,
        modality="mac",
        source="mac.app_activity",
        payload={
            "active_app": _frontmost_app(),
            "idle_seconds": _idle_seconds(),
        },
        meta_context_hint="waking",
    )


def write_snapshot(snap: FeatureSnapshot) -> None:
    """Persist a FeatureSnapshot to sensor_readings."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sensor_readings (user_id, kind, timestamp, payload)
            VALUES (%s, %s, %s, %s::jsonb)
            """,
            (
                snap.user_id,
                "mac_activity",
                snap.timestamp,
                json.dumps({
                    "source": snap.source,
                    **snap.payload,
                    "meta_context_hint": snap.meta_context_hint,
                }),
            ),
        )
        conn.commit()


def run_loop(*, user_id: str = DEFAULT_USER_ID, interval_s: int = 30) -> None:
    """Capture + write every `interval_s` seconds. Ctrl-C to stop."""
    logger.info("mac_sensors loop starting (interval=%ds)", interval_s)
    while True:
        try:
            snap = capture_once(user_id=user_id)
            write_snapshot(snap)
            logger.info(
                "tick app=%s idle=%.1fs",
                snap.payload["active_app"],
                snap.payload["idle_seconds"],
            )
        except Exception as e:
            logger.exception("tick failed: %s", e)
        time.sleep(interval_s)


def _cli() -> int:
    p = argparse.ArgumentParser(prog="capture.mac_sensors")
    p.add_argument("--once", action="store_true", help="Capture one snapshot and exit (don't loop, don't write).")
    p.add_argument("--interval", type=int, default=30)
    p.add_argument("--user-id", default=DEFAULT_USER_ID)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.once:
        snap = capture_once(user_id=args.user_id)
        print(json.dumps(snap.to_dict(), indent=2, default=str))
        return 0

    try:
        run_loop(user_id=args.user_id, interval_s=args.interval)
    except KeyboardInterrupt:
        print("stopped.", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(_cli())
```

- [ ] **Step 5: Run smoke test to verify it passes**

```bash
cd apps/inference && python -m capture.smoke_test
```
Expected: `FeatureSnapshot: {...}` showing `active_app=<some real app name>`, `idle_seconds=<a float>`, `modality=mac`. Ends with `OK`.

- [ ] **Step 6: Verify `--once` CLI works**

```bash
python -m capture.mac_sensors --once
```
Expected: JSON with `active_app` populated. No DB write.

- [ ] **Step 7: Run the loop for 30 seconds, then Ctrl-C**

```bash
timeout 35 python -m capture.mac_sensors --interval 10 || true
```

Verify two rows were written via Neon MCP:
```sql
SELECT recorded_at, payload->>'active_app' AS app
FROM sensor_readings
WHERE kind = 'mac_activity'
ORDER BY recorded_at DESC
LIMIT 5;
```
Expected: 3-4 recent rows.

- [ ] **Step 8: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/inference/capture/__init__.py apps/inference/capture/mac_sensors.py apps/inference/capture/smoke_test.py
git commit -m "$(cat <<'EOF'
feat(L1): Mac-as-sensor capture — active_app + idle_seconds

osascript reads frontmost app; ioreg reads HIDIdleTime (system idle since
last HID input). Writes to sensor_readings.kind='mac_activity' every 30s
(configurable). One-shot --once mode for testing without DB writes.

Smoke test verifies shape; loop verified end-to-end against Neon.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: BeliefState dataclass + per-axis writer — `apps/inference/fusion/`

**PR:** #5 (Fusion primitives). Single task = single PR. Depends on PR #2 (user_state_estimate shape). **Parallel with PR #4** — both can be worked simultaneously.

**Files:**
- Create: `apps/inference/fusion/__init__.py`
- Create: `apps/inference/fusion/belief_state.py`
- Create: `apps/inference/fusion/writer.py`
- Create: `apps/inference/fusion/test_belief_state.py`

**Why:** L3 fusion needs (a) a typed BeliefState bundling per-axis estimates with freshness, and (b) a writer that translates BeliefState updates into per-axis-row inserts on `user_state_estimate`. These are the primitives; the axis-specific fusion modules (Task 9-10) compose on top.

- [ ] **Step 1: Create `apps/inference/fusion/__init__.py`**

```python
"""L3 fusion layer — combines L2 FeatureSnapshots into per-axis BeliefState."""
from __future__ import annotations

from .belief_state import AxisEstimate, BeliefState
from .writer import write_axis_estimate

__all__ = ["AxisEstimate", "BeliefState", "write_axis_estimate"]
```

- [ ] **Step 2: Write the failing test**

Create `apps/inference/fusion/test_belief_state.py`:

```python
"""Tests for BeliefState + freshness policy."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fusion.belief_state import AxisEstimate, BeliefState


def _ts(offset_s: int = 0) -> datetime:
    return datetime(2026, 5, 27, 15, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_s)


def test_axis_estimate_fresh_default():
    est = AxisEstimate(
        axis="meta_context",
        value={"category": "waking/focused"},
        timestamp=_ts(0),
        confidence=0.8,
        source="L3.fusion.meta_context",
    )
    # default freshness threshold is 120s → fresh at "now=0"
    assert est.is_fresh(now=_ts(0)) is True
    assert est.is_fresh(now=_ts(60)) is True
    assert est.is_fresh(now=_ts(125)) is False


def test_axis_estimate_custom_fresh_window():
    est = AxisEstimate(
        axis="sleep_stage",
        value={"label": "rem"},
        timestamp=_ts(0),
        confidence=0.9,
        source="apple_health_sleep_stage",
        fresh_for_seconds=600,  # 10min for sleep
    )
    assert est.is_fresh(now=_ts(300)) is True
    assert est.is_fresh(now=_ts(700)) is False


def test_belief_state_get_returns_fresh_only():
    bs = BeliefState(user_id="u1")
    bs.update(AxisEstimate(
        axis="meta_context",
        value={"category": "waking"},
        timestamp=_ts(0),
        confidence=0.7,
        source="L3.fusion.meta_context",
    ))
    # fresh
    assert bs.get("meta_context", now=_ts(60)).value["category"] == "waking"
    # stale
    assert bs.get("meta_context", now=_ts(200)) is None


def test_belief_state_replaces_axis():
    bs = BeliefState(user_id="u1")
    bs.update(AxisEstimate(
        axis="meta_context",
        value={"category": "waking"},
        timestamp=_ts(0),
        confidence=0.7,
        source="L3.fusion.meta_context",
    ))
    bs.update(AxisEstimate(
        axis="meta_context",
        value={"category": "waking/focused"},
        timestamp=_ts(30),
        confidence=0.85,
        source="L3.fusion.meta_context",
    ))
    assert bs.get("meta_context", now=_ts(40)).value["category"] == "waking/focused"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd apps/inference && python -m pytest fusion/test_belief_state.py -v
```
Expected: `ModuleNotFoundError: No module named 'fusion.belief_state'`.

- [ ] **Step 4: Write the implementation**

Create `apps/inference/fusion/belief_state.py`:

```python
"""BeliefState + per-axis estimates with freshness policy.

Per ARCHITECTURE.md §3 L3: BeliefState holds the current best per-axis
estimates, each with a freshness window. Reads enforce freshness — stale
axes return None instead of letting callers act on outdated data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

DEFAULT_FRESH_SECONDS = 120


@dataclass
class AxisEstimate:
    """One per-axis state estimate produced by L3 fusion."""

    axis: str
    value: dict[str, Any]              # e.g., {"category": "waking/focused"} or {"label": "rem", "prob": 0.71}
    timestamp: datetime                # tz-aware UTC, when this estimate was *produced*
    confidence: float | None
    source: str                        # e.g., 'L3.fusion.meta_context', 'apple_health_sleep_stage'
    meta_context: str | None = None    # optional sub-tag if known
    i_model_id: str | None = None
    fresh_for_seconds: int = DEFAULT_FRESH_SECONDS

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("AxisEstimate.timestamp must be tz-aware UTC")

    def is_fresh(self, *, now: datetime | None = None) -> bool:
        if now is None:
            now = datetime.now(timezone.utc)
        return (now - self.timestamp).total_seconds() <= self.fresh_for_seconds


@dataclass
class BeliefState:
    """Per-user bundle of current per-axis estimates with freshness gates."""

    user_id: str
    estimates: dict[str, AxisEstimate] = field(default_factory=dict)

    def update(self, est: AxisEstimate) -> None:
        """Replace the current estimate for the given axis."""
        self.estimates[est.axis] = est

    def get(self, axis: str, *, now: datetime | None = None) -> AxisEstimate | None:
        """Return the axis estimate iff it's fresh; else None."""
        est = self.estimates.get(axis)
        if est is None:
            return None
        return est if est.is_fresh(now=now) else None

    def snapshot(self, *, now: datetime | None = None) -> dict[str, dict[str, Any]]:
        """Dict of {axis: value_dict} for fresh axes only — for prompt assembly."""
        out: dict[str, dict[str, Any]] = {}
        for axis, est in self.estimates.items():
            if est.is_fresh(now=now):
                out[axis] = {
                    "value": est.value,
                    "confidence": est.confidence,
                    "source": est.source,
                    "timestamp": est.timestamp.isoformat(),
                }
        return out
```

Create `apps/inference/fusion/writer.py`:

```python
"""Per-axis-row writer for user_state_estimate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from .belief_state import AxisEstimate


def write_axis_estimate(user_id: str, est: AxisEstimate) -> str:
    """Insert one per-axis-row into user_state_estimate. Returns new id."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_state_estimate
              (user_id, axis, timestamp, value, confidence, source, meta_context, i_model_id)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id,
                est.axis,
                est.timestamp,
                json.dumps(est.value),
                est.confidence,
                est.source,
                est.meta_context,
                est.i_model_id,
            ),
        )
        new_id = str(cur.fetchone()[0])
        conn.commit()
    return new_id
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd apps/inference && python -m pytest fusion/test_belief_state.py -v
```
Expected: `4 passed`.

- [ ] **Step 6: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/inference/fusion/__init__.py apps/inference/fusion/belief_state.py apps/inference/fusion/writer.py apps/inference/fusion/test_belief_state.py
git commit -m "$(cat <<'EOF'
feat(L3): BeliefState + per-axis writer

AxisEstimate dataclass with freshness gate (default 120s, override per
axis). BeliefState holds per-axis estimates, read-time freshness check
returns None for stale axes. writer.write_axis_estimate persists to the
per-axis-row user_state_estimate (migration 0009).

4 tests passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: meta_context axis fusion — `apps/inference/fusion/axes/meta_context.py`

**PR:** #6 (meta_context axis). Single task = single PR. Depends on PR #4 (mac_activity data) + PR #5 (AxisEstimate). **Parallel with PR #7.**

**Files:**
- Create: `apps/inference/fusion/axes/__init__.py`
- Create: `apps/inference/fusion/axes/meta_context.py`
- Create: `apps/inference/fusion/axes/test_meta_context.py`

**Why:** Need at least one *waking* L3 axis lit by end of Week 1 to validate the pipeline end-to-end. `meta_context` is the most foundational (per commitment #14 it biases every other layer), and it can be computed from Mac sensor data alone — no biometric fusion needed yet.

**Logic:** Read recent `mac_activity` sensor_readings, derive a coarse waking sub-state from idle time + app category. v1 rules (fixed heuristic; learned model is post-MVP):

| Rule | Result |
|---|---|
| idle_seconds > 300 | `meta_context = waking/idle` |
| active_app in {Cursor, Terminal, iTerm, Code, VS Code, IntelliJ, PyCharm} AND idle_seconds < 60 | `waking/focused` |
| active_app in {Mail, Slack, Discord, Messages, Telegram} | `waking/communicating` |
| active_app in {YouTube, Netflix, Spotify, Music} | `waking/consuming` |
| active_app in {Safari, Chrome, Firefox, Arc} | `waking/browsing` |
| Otherwise | `waking/other` |

- [ ] **Step 1: Create `apps/inference/fusion/axes/__init__.py`**

```python
"""Per-axis L3 fusion modules."""
```

- [ ] **Step 2: Write the failing test**

Create `apps/inference/fusion/axes/test_meta_context.py`:

```python
"""Tests for meta_context axis fusion."""
from __future__ import annotations

from datetime import datetime, timezone

from fusion.axes.meta_context import classify_meta_context


def test_idle_long():
    out = classify_meta_context(active_app="Cursor", idle_seconds=400)
    assert out["category"] == "waking/idle"


def test_focused_coding():
    out = classify_meta_context(active_app="Cursor", idle_seconds=5)
    assert out["category"] == "waking/focused"


def test_communicating():
    out = classify_meta_context(active_app="Slack", idle_seconds=2)
    assert out["category"] == "waking/communicating"


def test_browsing():
    out = classify_meta_context(active_app="Arc", idle_seconds=10)
    assert out["category"] == "waking/browsing"


def test_consuming():
    out = classify_meta_context(active_app="YouTube", idle_seconds=15)
    assert out["category"] == "waking/consuming"


def test_other_falls_through():
    out = classify_meta_context(active_app="Finder", idle_seconds=2)
    assert out["category"] == "waking/other"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd apps/inference && python -m pytest fusion/axes/test_meta_context.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Write the implementation**

Create `apps/inference/fusion/axes/meta_context.py`:

```python
"""meta_context axis fusion — coarse waking sub-state from Mac sensors.

v1 fixed-heuristic. Learned categorization post-MVP. See Week-1 plan for
the rule table.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

INF_DIR = Path(__file__).resolve().parent.parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from ..belief_state import AxisEstimate

CODING_APPS = {
    "Cursor", "Terminal", "iTerm", "Code", "Visual Studio Code",
    "IntelliJ IDEA", "PyCharm", "Xcode", "Sublime Text", "Vim", "Neovim", "Zed",
}
COMMUNICATING_APPS = {
    "Mail", "Slack", "Discord", "Messages", "Telegram", "Microsoft Teams",
    "WhatsApp", "Signal", "Zoom",
}
CONSUMING_APPS = {
    "YouTube", "Netflix", "Spotify", "Music", "Apple TV", "TV", "Hulu", "Twitch",
}
BROWSING_APPS = {"Safari", "Chrome", "Google Chrome", "Firefox", "Arc", "Edge", "Brave Browser"}

IDLE_THRESHOLD_S = 300
ACTIVE_IDLE_MAX_S = 60


def classify_meta_context(*, active_app: str, idle_seconds: float) -> dict[str, Any]:
    """Apply v1 heuristic. Returns {category, reason}."""
    if idle_seconds > IDLE_THRESHOLD_S:
        return {"category": "waking/idle", "reason": f"idle {int(idle_seconds)}s > {IDLE_THRESHOLD_S}s"}

    if active_app in CODING_APPS and idle_seconds < ACTIVE_IDLE_MAX_S:
        return {"category": "waking/focused", "reason": f"coding app + active <{ACTIVE_IDLE_MAX_S}s idle"}

    if active_app in COMMUNICATING_APPS:
        return {"category": "waking/communicating", "reason": "communication app"}

    if active_app in CONSUMING_APPS:
        return {"category": "waking/consuming", "reason": "media app"}

    if active_app in BROWSING_APPS:
        return {"category": "waking/browsing", "reason": "browser"}

    return {"category": "waking/other", "reason": f"unrecognized app: {active_app}"}


def fuse_recent(
    *,
    user_id: str,
    now: datetime | None = None,
    window_seconds: int = 60,
) -> AxisEstimate | None:
    """Pull the latest mac_activity reading in window_seconds and classify.

    Returns None if no Mac sensor data is present in the window.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=window_seconds)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT recorded_at, payload
            FROM sensor_readings
            WHERE user_id = %s
              AND kind = 'mac_activity'
              AND recorded_at >= %s
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (user_id, window_start),
        )
        row = cur.fetchone()

    if row is None:
        return None

    ts, payload = row
    active_app = payload.get("active_app", "unknown")
    idle_seconds = float(payload.get("idle_seconds", 0))

    cls = classify_meta_context(active_app=active_app, idle_seconds=idle_seconds)
    return AxisEstimate(
        axis="meta_context",
        value=cls,
        timestamp=ts,
        confidence=0.65,  # v1 heuristic — moderate confidence
        source="L3.fusion.meta_context.v1_heuristic",
        meta_context=cls["category"],
        fresh_for_seconds=120,
    )
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd apps/inference && python -m pytest fusion/axes/test_meta_context.py -v
```
Expected: `6 passed`.

- [ ] **Step 6: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/inference/fusion/axes/__init__.py apps/inference/fusion/axes/meta_context.py apps/inference/fusion/axes/test_meta_context.py
git commit -m "$(cat <<'EOF'
feat(L3): meta_context axis — coarse waking sub-state from Mac sensors

v1 fixed-heuristic mapping (active_app, idle_seconds) → one of:
waking/focused, waking/communicating, waking/consuming, waking/browsing,
waking/idle, waking/other. classify_meta_context() is pure; fuse_recent()
pulls latest mac_activity reading from sensor_readings.

6 tests passing. Learned categorization post-MVP.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: sleep_stage axis fusion — `apps/inference/fusion/axes/sleep_stage.py`

**PR:** #7 (sleep_stage axis). Single task = single PR. Depends on PR #3 (apple_health_sleep_stage data) + PR #5 (AxisEstimate). **Parallel with PR #6.**

**Files:**
- Create: `apps/inference/fusion/axes/sleep_stage.py`
- Create: `apps/inference/fusion/axes/test_sleep_stage.py`

**Why:** The other Week-1 exit axis. Reads Apple Health-labeled sleep stages from sensor_readings and emits a current `sleep_stage` AxisEstimate. Long fresh window (10min) because sleep stages are inherently slow-changing. When not in a sleep window, the axis falls back to OFFLINE per the spec.

- [ ] **Step 1: Write the failing test**

Create `apps/inference/fusion/axes/test_sleep_stage.py`:

```python
"""Tests for sleep_stage axis fusion (pure-logic part)."""
from __future__ import annotations

from datetime import datetime, timezone

from fusion.axes.sleep_stage import classify_sleep_stage


def test_active_stage():
    out = classify_sleep_stage(stage="rem", duration_s=600, source="Apple Watch")
    assert out["label"] == "rem"
    assert out["active"] is True


def test_awake_in_bed_classified_as_offline():
    out = classify_sleep_stage(stage="in_bed", duration_s=120, source="Apple Watch")
    assert out["label"] == "in_bed"
    assert out["active"] is False  # not actually sleeping


def test_awake_offline():
    out = classify_sleep_stage(stage="awake", duration_s=300, source="Apple Watch")
    assert out["label"] == "awake"
    assert out["active"] is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/inference && python -m pytest fusion/axes/test_sleep_stage.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

Create `apps/inference/fusion/axes/sleep_stage.py`:

```python
"""sleep_stage axis fusion — current sleep stage from Apple Health labels.

Reads the most recent `apple_health_sleep_stage` row whose [start,end] window
covers `now`. Emits OFFLINE (returns None) if no such window.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INF_DIR = Path(__file__).resolve().parent.parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from ..belief_state import AxisEstimate

# Stages where the user is actually asleep (vs. just in bed or awake-in-bed).
ACTIVE_SLEEP_STAGES = {"core", "deep", "rem", "asleep", "asleep_legacy"}


def classify_sleep_stage(*, stage: str, duration_s: int, source: str) -> dict[str, Any]:
    """Wrap an Apple Health sleep label into our axis value shape."""
    return {
        "label": stage,
        "active": stage in ACTIVE_SLEEP_STAGES,
        "duration_s": duration_s,
        "source": source,
    }


def fuse_recent(
    *,
    user_id: str,
    now: datetime | None = None,
) -> AxisEstimate | None:
    """Find the apple_health_sleep_stage row whose [start, end] covers `now`.

    Returns AxisEstimate if covered; None otherwise (= OFFLINE).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT recorded_at, payload
            FROM sensor_readings
            WHERE user_id = %s
              AND kind = 'apple_health_sleep_stage'
              AND recorded_at <= %s
              AND (payload->>'end')::timestamptz >= %s
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (user_id, now, now),
        )
        row = cur.fetchone()

    if row is None:
        return None

    ts, payload = row
    cls = classify_sleep_stage(
        stage=payload.get("stage", "unknown"),
        duration_s=int(payload.get("duration_s", 0)),
        source=payload.get("source", ""),
    )
    return AxisEstimate(
        axis="sleep_stage",
        value=cls,
        timestamp=ts,
        confidence=0.95,  # AH labels are direct watch output
        source="apple_health_sleep_stage",
        meta_context="sleep" if cls["active"] else None,
        fresh_for_seconds=600,  # 10min — stages are slow
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd apps/inference && python -m pytest fusion/axes/test_sleep_stage.py -v
```
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/inference/fusion/axes/sleep_stage.py apps/inference/fusion/axes/test_sleep_stage.py
git commit -m "$(cat <<'EOF'
feat(L3): sleep_stage axis — current Apple Health label or OFFLINE

Reads apple_health_sleep_stage rows from sensor_readings; finds the window
covering `now`. Returns AxisEstimate (10min freshness) if covered, None
(= OFFLINE) otherwise. classify_sleep_stage() distinguishes active sleep
(core/deep/rem/asleep) from passive states (in_bed/awake).

3 tests passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: End-to-end fusion smoke test

**PR:** #8 (End-to-end smoke + Week-1 closeout). Cluster with Task 12. Depends on PRs #6 + #7 merged.

**Files:**
- Create: `apps/inference/fusion/smoke_test.py`

**Why:** Validates the whole Week-1 pipeline against real data: capture Mac activity → write sensor_readings → fuse meta_context + sleep_stage → write per-axis-row → read back BeliefState → confirm shape.

- [ ] **Step 1: Write the smoke test**

Create `apps/inference/fusion/smoke_test.py`:

```python
"""End-to-end Week-1 smoke test.

Sequence:
  1. Capture one Mac sensor reading (writes to sensor_readings).
  2. Run meta_context fusion → produce AxisEstimate.
  3. Run sleep_stage fusion → produce AxisEstimate or None.
  4. Write each estimate to user_state_estimate (per-axis-row).
  5. Read back the recent BeliefState; assert axes present.

Run:
    cd apps/inference && python -m fusion.smoke_test
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

INF_DIR = Path(__file__).resolve().parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from db import get_conn  # noqa: E402

from capture.mac_sensors import capture_once, write_snapshot  # noqa: E402
from fusion.axes import meta_context as mc_axis  # noqa: E402
from fusion.axes import sleep_stage as ss_axis  # noqa: E402
from fusion.belief_state import BeliefState  # noqa: E402
from fusion.writer import write_axis_estimate  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


def main() -> int:
    now = datetime.now(timezone.utc)
    user_id = DEFAULT_USER_ID

    # 1. Capture Mac sensor reading (writes one sensor_readings row).
    snap = capture_once(user_id=user_id)
    write_snapshot(snap)
    print(f"[1/5] mac_activity captured: app={snap.payload['active_app']} idle={snap.payload['idle_seconds']:.1f}s")

    # 2. Fuse meta_context.
    mc_est = mc_axis.fuse_recent(user_id=user_id, now=now)
    assert mc_est is not None, "meta_context fusion returned None — Mac sensor write must have failed"
    print(f"[2/5] meta_context fused: {mc_est.value['category']} (conf={mc_est.confidence})")

    # 3. Fuse sleep_stage (may legitimately be None if not currently in sleep).
    ss_est = ss_axis.fuse_recent(user_id=user_id, now=now)
    if ss_est is None:
        print("[3/5] sleep_stage: OFFLINE (no covering window — expected if awake)")
    else:
        print(f"[3/5] sleep_stage fused: {ss_est.value['label']} (active={ss_est.value['active']})")

    # 4. Write to user_state_estimate.
    mc_id = write_axis_estimate(user_id, mc_est)
    print(f"[4/5] meta_context written to user_state_estimate id={mc_id}")
    if ss_est is not None:
        ss_id = write_axis_estimate(user_id, ss_est)
        print(f"[4/5] sleep_stage written to user_state_estimate id={ss_id}")

    # 5. Read back as BeliefState and assert axes present + fresh.
    bs = BeliefState(user_id=user_id)
    bs.update(mc_est)
    if ss_est is not None:
        bs.update(ss_est)

    fresh = bs.snapshot(now=now)
    print(f"[5/5] BeliefState snapshot: {fresh}")
    assert "meta_context" in fresh, "meta_context missing from BeliefState"

    # Verify per-axis-row was persisted with correct shape via DB query.
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT axis, value, confidence, source, meta_context
            FROM user_state_estimate
            WHERE user_id = %s AND id = %s
            """,
            (user_id, mc_id),
        )
        db_row = cur.fetchone()

    assert db_row is not None, "wrote meta_context row but couldn't read it back"
    axis, value, confidence, source, meta_context_col = db_row
    assert axis == "meta_context"
    assert value["category"].startswith("waking/")
    print(f"[5/5] DB readback: axis={axis} value={value} meta_context={meta_context_col}")

    print("\nOK — Week 1 end-to-end fusion smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the smoke test**

```bash
cd apps/inference && python -m fusion.smoke_test
```
Expected output: All 5 steps print success. Final line: `OK — Week 1 end-to-end fusion smoke test passed.`

If sleep_stage fusion returns None, that's fine as long as you're awake — it means no covering window exists in `sensor_readings`. To force a positive result, ensure you've recently run `bin/sync_hk_export.py` to pull at least one night's sleep stages.

- [ ] **Step 3: Verify the per-axis row landed in Neon**

Run via Neon MCP:
```sql
SELECT axis, value, confidence, source, meta_context, timestamp
FROM user_state_estimate
WHERE user_id = '61c18d4c-1c20-408a-bd5f-f5f88fd9922f'
ORDER BY created_at DESC
LIMIT 5;
```
Expected: the just-written `meta_context` row appears with `value->>'category'` like `waking/focused`.

- [ ] **Step 4: Commit**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add apps/inference/fusion/smoke_test.py
git commit -m "$(cat <<'EOF'
test(L3): end-to-end Week-1 fusion smoke test

Captures Mac sensor → writes sensor_readings → fuses meta_context +
sleep_stage axes → writes per-axis-row to user_state_estimate → reads
back as BeliefState + via direct DB query. Asserts shape at each step.

Validates the full Week-1 pipeline. Run:
  cd apps/inference && python -m fusion.smoke_test

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Week 1 closeout — update STATUS.md + REBUILD_PLAN.md + tag

**PR:** #8 (End-to-end smoke + Week-1 closeout). **Final task in PR #8** — open + merge PR at end of this task. Then tag `mvp-week-1-end` on `main` after PR #8 merges.

**Files:**
- Modify: `docs/STATUS.md`
- Modify: `docs/REBUILD_PLAN.md`
- Tag: `mvp-week-1-end`

**Why:** Per CLAUDE.md convention: "Always update `docs/STATUS.md` after substantive work lands. Date the change at the top." And per the spec: "Tag `mvp-week-1-end`" to provide a rollback anchor.

- [ ] **Step 1: Update STATUS.md**

Open `docs/STATUS.md` and add a new dated section at the top (under the existing rebuild banner). Use this template:

```markdown
## 2026-06-03 — MVP Week 1 complete

**Shipped this week:**
- Migration 0009: per-axis-row `user_state_estimate` + `prediction_log` + sensor_readings consent columns. Applied via Neon MCP; backfill verified.
- `bin/sync_hk_export.py` — incremental Apple Health → sensor_readings, idempotent.
- `apps/inference/capture/mac_sensors.py` — active_app + idle_seconds loop, 30s tick.
- `apps/inference/features/snapshot.py` — FeatureSnapshot L2 envelope.
- `apps/inference/fusion/` — BeliefState + per-axis writer + meta_context + sleep_stage axes.
- End-to-end smoke: `python -m fusion.smoke_test` writes per-axis rows from live Mac sensor + Apple Health data.
- Fixed pre-existing python-multipart gap so FastAPI bridge can start.

**Two L3 axes live:** `meta_context`, `sleep_stage`. Other axes (arousal_inferred, state_declared, audio_social_context, cognitive_load) defer to Weeks 2-3.

**What runs tonight:**
- Everything from prior `STATUS.md` (recall.capture, etc.) plus:
- `python -m capture.mac_sensors` (loops, writes mac_activity every 30s)
- `bin/sync_hk_export.py <path/to/export.xml>` (idempotent Apple Health sync)
- `python -m fusion.smoke_test` (full Week-1 pipeline end-to-end)

**Next:** Week 2 — re-pull TTS chain from v0-pre-rebuild tag; OpenWakeWord + wake-word→STT→chat→TTS roundtrip. Per `docs/superpowers/specs/2026-05-27-vertical-slice-waking-empath-design.md` §8.
```

(Adjust the date if Week 1 takes longer/shorter.)

- [ ] **Step 2: Update REBUILD_PLAN.md**

Open `docs/REBUILD_PLAN.md` and mark Week 1 / Phase 1 milestones as complete. Match whatever checkbox / status convention is already used in that file. Add a brief reflection on what slipped vs landed.

- [ ] **Step 3: Commit doc updates**

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook"
git add docs/STATUS.md docs/REBUILD_PLAN.md
git commit -m "$(cat <<'EOF'
docs: MVP week 1 complete — schema + sensor writers + first 2 axes lit

Two L3 axes (meta_context, sleep_stage) writing per-axis-row to
user_state_estimate from live Mac sensors + Apple Health data. End-to-end
fusion smoke test passing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Tag the week**

```bash
git tag -a mvp-week-1-end -m "MVP Week 1 complete: schema (migration 0009) + watch sync + Mac sensors + meta_context + sleep_stage axes"
git push origin main
git push origin mvp-week-1-end
```

- [ ] **Step 5: Verify the tag is visible on origin**

```bash
git ls-remote --tags origin | grep mvp-week-1-end
```
Expected: one line showing the tag's SHA on origin.

---

## After Week 1

You've now landed:
- The per-axis-row schema migration with backfill (#13, §3 L3)
- Apple Health incremental sync (live writer path that replaces deleted iOS)
- Mac-as-sensor capture (cheapest waking sensor)
- L2 FeatureSnapshot envelope (uniform shape downstream)
- L3 BeliefState + freshness policy + per-axis writer
- Two L3 axes (`meta_context`, `sleep_stage`)
- End-to-end smoke test exercising the full pipeline
- Pre-existing python-multipart fix as a bonus

**The system is now reading the user's waking context for the first time.** It's quiet — no Regis output yet, no decisions, no interject — but the substrate that everything else builds on is live and writing data every 30 seconds.

Next planning session should write Week 2: re-pull TTS chain, OpenWakeWord, wake-word→STT→chat→TTS roundtrip, composer reads BeliefState. The spec section 8 Week 2 has the exit criteria.
