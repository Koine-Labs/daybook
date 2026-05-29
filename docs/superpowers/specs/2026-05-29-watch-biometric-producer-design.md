# Live Apple-Watch biometric producer — design

**Date:** 2026-05-29
**Status:** approved (design forks settled with founder)
**Piece:** the next major build toward the waking-distributed MVP (candidate B from the `daybook-next-major-piece` workflow). A live biometric producer wires watch HR/HRV onto the L1–L6 bus — the only candidate that discharges commitment **#14**'s day-and-night biometric accrual *on the bus*, and the densest continuous latent-state series the JEPA encoder (#16) will train on.

## Context

The L2/L4 biometric REM lane is **built and idle**: `features/biometric.py` (L2) turns a windowed biometric `SignalPacket` into the 24 frozen REM feature_cols, and `prediction/feature_participant.py` (L4) scores it into a `rem` `Prediction`. Nothing produces those packets — there is no L1 biometric producer. This piece is the missing producer.

**Ground truth (verified on disk, not docs):**
- There is **no live Watch HealthKit stream** — `HeartRateClient.swift` (described in CLAUDE.md) is **not tracked**; the watch app has no committed source. `realtime.py` was scrapped in the rebuild. So "live off-watch HR" is blocked on the absent iOS/Watch app.
- Real biometrics **already exist in the DB**: `parse_apple_health.py` imported ~10 yr of readings into `sensor_readings` under bare-name kinds.
- The REM model trains on bare-name kinds `heart_rate / hrv / respiratory_rate / spo2` with payload value fields `bpm / rmssdMs / breathsPerMinute / percent` (`classifier/data.py:19-22,124`). `classifier.data` has the loaders — reuse them.
- `sensors/participant.py:27` already maps `BIOMETRIC → CONSENT_SCOPES['hk']` — no new consent mapping.
- `features/biometric.py` expects payload `{epoch_start_at, readings:[{recorded_at,kind,value}], session_started_at?, hr_mean_history?}`, with `EPOCH_SECONDS=30`, `CONTEXT_SECONDS=300`; HR-lag features come from `hr_mean_history` (oldest-first, `history[-k]`).

**Settled forks (founder):**
1. **Data source:** build the **DB-replay bridge now** (stream real imported readings onto the bus, off-CI) *plus* a synthetic generator for CI — proving the lane on real biometrics this week.
2. **REM gating:** **gate the L4 REM scorer to the SLEEP meta-context** in this piece. Biometrics still accrue under both Waking and Sleep (#14), but waking HR no longer yields a meaningless `rem` belief.

## Design

### New: `sensors/watch_adapter.py` (CI-safe, transport-agnostic — mirrors `AudioBusSink`)
- **`WatchBusSink`** — holds only a `MessageBus` (+ `user_id`, `meta_context=UNKNOWN` default, like `AudioBusSink`). `emit_window(*, epoch_start_at, readings, session_started_at=None, hr_mean_history=None, user_id=None) -> MessageEnvelope`: builds the `features/biometric.py` payload shape → `IntentTaggedReading(modality=BIOMETRIC, intent=CONTINUOUS, kind=KIND_BIOMETRIC_WINDOW, source=WATCH_SOURCE)` → `sensors.participant.emit(bus, reading, meta_context=self.meta_context)`. Transport-agnostic: identical code over `InProcessTransport` (today) and `NetworkTransport` (watch-as-satellite later).
- **`window_readings(readings, *, epoch_seconds=30, context_seconds=300) -> Iterator[dict]`** — pure: a time-ordered flat list of `{recorded_at, kind, value}` → successive epoch window payloads, each carrying its preceding `context_seconds` of readings and an `hr_mean_history` (oldest-first prior-epoch hr_means) computed exactly as `features/biometric.py._lag_value` consumes it. tz-aware UTC enforced; empty/short input degrades (no fabricated values), never crashes.
- **`synthesize_biometric_window(*, epoch_start_at, ...) -> dict`** — deterministic synthetic window (mirrors `bci.eeg_adapter.synthesize_eeg_window`) for CI + demo, no DB. Varies by an index/seed arg, not `Math.random`.
- Constants: `KIND_BIOMETRIC_WINDOW = "biometric_window"`, `WATCH_SOURCE = "watch.biometric_window"` (matches `features/biometric.py.SOURCE`). Reuse `EPOCH_SECONDS`/`CONTEXT_SECONDS` from `features.biometric` (single source of truth — do not redefine).

### New: `runtime/biometric_replay.py` (off-CI — needs DB; `runtime/` is not collected by CI)
- `build_biometric_lane(bus) -> MessageBus`: register the L2 biometric extractor (`features.participant`) + the L4 feature participant (`prediction.feature_participant`) onto a bus.
- `replay_session(session_id, *, bus, user_id=DEFAULT_USER_ID)`: reuse `classifier.data` loaders to read a sleep session's bare-name readings, `window_readings(...)` them, and push each through `WatchBusSink(bus, meta_context=SLEEP)`. Lazy DB import (import-clean with no `DATABASE_URL`, like `runtime/waking_arc.py`).
- `main()`: replay one recent labeled sleep session as a real-data smoke.

### Edit: `prediction/feature_participant.py` (CI path) — REM gate (#14)
- In `handle_feature`, after the biometric-snapshot checks, **fire only when `inbound.meta_context == MetaContext.SLEEP`**; otherwise return `None` (degrade, never crash). Import `MetaContext`. Update the module docstring: the REM nowcaster is SLEEP-only (#14 — L4 selects different models per meta-context).

## Test plan
- **CI-safe** (`sensors/` + `prediction/`, on the CI path `pytest core sensors features fusion prediction decision output bci`):
  - `window_readings`: epoch/context boundaries, `hr_mean_history` correctness vs `_lag_value`, tz-aware enforcement, empty/short degrade.
  - `synthesize_biometric_window`: shape + determinism.
  - **End-to-end (no DB):** a synthetic window through `WatchBusSink(meta_context=SLEEP)` → `TOPIC_SIGNAL` → L2 24-feature snapshot → L4 `rem` `Prediction`; the same window under `WAKING`/`UNKNOWN` → **no** `Prediction` (gate regression).
  - trace_id / meta_context / consent_scope (`hk`) / i_model_id propagate L1→L4 (#1/#11/#14).
- **Off-CI:** `python -m runtime.biometric_replay` replays a real session end-to-end (manual smoke).

## Commitments touched
- **#14** — primary: biometric data accrues on the bus day and night; REM scorer gated to SLEEP.
- **#11** — semantic-first: only derived readings ride the bus, never raw waveform.
- **#16** — accrues the dense continuous latent-state series the world-model encoder trains on.
- **#1** — `i_model_id` propagates through the producer.
- **#9** — transport-agnostic producer: the same code becomes the watch-satellite producer over `NetworkTransport`.

## Risks / notes
- The REM model is a *sleep* nowcast — the SLEEP gate is the correctness fix, not optional.
- Replay needs sessions with sleep-stage labels; `classifier.data` already filters those (`n_stage_segments >= …`).
- Windowing must mirror `compute_session_features` expectations (300s context / 30s epoch) — reuse the constants, don't fork them.
- First cut is a **DB-replay bridge**, not a true off-watch stream (the watch app is absent). Still a real live bus producer satisfying #14; swaps to a real stream when the iOS/Watch HealthKit app lands, with no change to `WatchBusSink` (transport-agnostic).
