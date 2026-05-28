# Daybook MVP — Vertical Slice Waking Empath

**Date:** 2026-05-27
**Owner:** Aakash Agrawal (Koine Labs)
**Status:** Design spec — implementation plan to follow
**Source of truth:** [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md) (16 commitments, 6-layer design)
**Sequencing context:** [`docs/REBUILD_PLAN.md`](../../REBUILD_PLAN.md) (this spec realizes Phases 1-6 of that plan; Phase 0 already complete)

---

## 1. Goal

Ship the thinnest end-to-end **waking-empath loop** that lights every architectural commitment at minimum width before fattening any single layer. Target: **4-5 weeks solo**.

The shipped system:

- Reads the user's body continuously via **watch + mic + Mac sensors** (plus EEG if the BioAmp arrives in time).
- Maintains a per-axis **Contextual Map** (the BeliefState) updated every 30 seconds.
- Lets **Regis respond to voice or text** in a tone shaped by current physiological + behavioral state.
- Logs every Regis action and its outcome to `prediction_log` for later learned-action-selection (#13).

This MVP is the **substrate proof**, not the destination. Validating it is what unlocks: clinical extension, wearable form factor, full I-Model self-expansion (#6), JEPA world model (#16), and causal reasoning (#15).

---

## 2. Validation wedge

**Inherited from POSITIONING.md (still on):** ≥50% improvement in weekly dream recall vs 14-day pre-baseline, N=1 (Aakash), 60-90 days. Already working tonight via `python -m recall.capture`.

**Added MVP-specific success criteria:**

1. **Tone-calibrated responses.** Manual review of 20 Regis chat exchanges across one week shows demonstrable difference in tone/length based on inferred `meta_context` (focused vs winding-down vs exerting). Subjectively obvious in side-by-side comparison.
2. **State-aware retrieval.** Regis's response references `state_declared` (things the user told her) in ≥80% of relevant chat exchanges.
3. **Outcome data accumulating.** `prediction_log` has ≥50 rows after 2 weeks of normal use — enough to start outcome analysis post-MVP, even though we don't train on it yet.
4. **Trajectory recall.** "Regis, how was Tuesday?" produces a per-axis-trajectory answer, not a generic vibes summary.

---

## 3. Architectural commitments — MVP depth per commitment

All 16 ARCHITECTURE.md commitments are honored. Several are present as schema + interface only; full implementation lands post-MVP. Documenting depth per commitment forces explicit deferral decisions instead of accidental drift.

| # | Commitment | MVP depth |
|---|---|---|
| 1 | I-Model polymorphism (`i_model_id NULL` everywhere) | **Schema present.** All new tables in 0009 honor the column. |
| 2 | Content polymorphism (`kind` + `payload JSONB`) | **Active.** New `audio_semantic` kind added to `sensor_readings` contract. |
| 3 | Wisp-as-interface (audio primary, screens for debug) | **Active.** Bone-conduction TTS is primary surface; CLI for dev. |
| 4 | Three I-Models (user_self, regis_of_user, regis_self) | **Schema + seed clusters only.** Three top-level containers seeded; sub-cluster discovery deferred. |
| 5 | Dual-mode Regis (Witness/Companion, biased by L3) | **Active.** Composer selects mode from BeliefState (`meta_context`). |
| 6 | Self-expanding I-Models (clusters discovered, not pre-defined) | **Deferred.** Migration 0009 keeps existing cluster schema; clustering pipeline post-MVP. |
| 7 | Moment polymorphism (`regis_moments.kind`) | **Active.** Already in place from prior schema. |
| 8 | Generative Regis from day one (PERSONA.md is system prompt) | **Active.** Already in place. |
| 9 | Continuous build — v1 IS v3 substrate | **Active.** MVP shape directly extends to wearable form factor; no scaffolding to throw away. |
| 10 | Input = Intent × Modality | **Active across explicit voice/text + continuous biometric/audio.** Visual continuous deferred. |
| 11 | Semantic-first continuous sensing | **Audio lit in MVP** (VAD/diarization/prosody/ambient). Visual deferred to post-MVP. |
| 12 | Native clients via FastAPI bridge | **Preserved.** Bridge still serves `/state`, `/recall`, etc.; no new native client built in MVP. |
| 13 | Outcome-driven action selection | **`prediction_log` schema lands; fixed-weight v1 policy.** Thompson bandit unlocked post-MVP once ~50+ outcomes accumulate. |
| 14 | Meta-context biases every layer | **Active.** Waking + Sleep meta-contexts both lit; sub-contexts populated. |
| 15 | Regis as modeled controlled variable | **Interface preserves `action` param at L4.** v1 prediction implementations use naive action-conditioning placeholders. Causal modeling deferred. |
| 16 | JEPA world model (LeWM target) | **L4 interface shaped per §2.16.** v1 implementations are per-axis regression scaffolds. Encoder/predictor/SIGReg/CEM all deferred to v2 as data accumulates. |

---

## 4. Sensor scope + phasing

| Sensor | Source | MVP week | Axes it feeds |
|---|---|---|---|
| **Apple Watch S8** (HR, HRV, motion, sleep stages) | Apple Health XML export → `bin/sync_hk_export.py` | Week 1 | `arousal_inferred`, `sleep_stage` |
| **Apple Health historical sleep stages** | Existing 10yr data already in Neon | Week 1 | `sleep_stage` (replay + current) |
| **Mac sensors** (active app, keystrokes/min, last_break_at, session_duration) | AppleScript daemon → `apps/inference/capture/mac_sensors.py` | Week 2 | `meta_context` (waking sub-states) |
| **External mic — wake-word path** | OpenWakeWord → `llm/stt_streaming.transcribe_streaming()` | Week 2 | (drives the conversation surface) |
| **External mic — continuous semantic** | VAD (Silero) + speaker embedding + librosa prosody + YAMNet ambient | Week 3 | `audio_social_context`, refines `arousal_inferred` |
| **BioAmp EXG → EEG** (forehead band, alpha/beta/theta) | Pi or USB-serial → semantic packets every 1s | Week 2-3 **stretch** | `cognitive_load` (5th axis) |

**Deferred to post-MVP (architecture absorbs without rework):**
- Cam (visual semantic packets — YOLOv8n + MediaPipe Pose + Face Mesh)
- iPhone sensors (no iOS client until v1.5+)
- Walking-context biometric streams
- Multi-channel EEG, EMG, ECG (single-channel EXG only in MVP)

---

## 5. Privacy / consent policy (locked decision)

Continuous mic (and eventually cam) creates exposure when others are in the home. **MVP runs under Policy #1 — pause-on-other-voice:**

- VAD + speaker embedding determines speaker identity per utterance.
- **Non-Aakash voice detected:** write `social_context: with_other` packet only. Pause prosody, ambient, and any STT for the duration of the non-Aakash voice window plus a 30-second silence buffer.
- **Only Aakash (or silence):** full pipeline runs.

**Consent metadata** in migration 0009 records what was opted-in at write time (`mic_continuous_opt_in_at`, future `cam_continuous_opt_in_at`, etc.) so policy evolution doesn't lose audit trail.

Re-evaluate at week 5: if "pause on other voice" silently loses too much data (e.g., Aakash is alone 95% of the time and the conservative default never helps), promote to Policy #2 (log "other_voice_present + duration" without prosody).

---

## 6. Schema changes — migration 0009

Migration `0009_per_axis_state_and_prediction_log.sql` adds three changes in one transaction:

### 6a. Reshape `user_state_estimate` (wide-row → per-axis-row)

**Current (wide-row, from v0):**
```sql
user_state_estimate(user_id, ts, stage_proba, arousal, valence, ...)
```

**Target (per-axis-row, per ARCHITECTURE.md §3 L3):**
```sql
user_state_estimate(
  id              uuid PRIMARY KEY,
  user_id         uuid NOT NULL,
  axis            text NOT NULL,              -- 'arousal_inferred', 'meta_context', 'sleep_stage', etc.
  timestamp       timestamptz NOT NULL,
  value           jsonb NOT NULL,             -- {"category": "focused"} or {"scalar": 0.55}
  confidence      double precision,
  source          text,                       -- 'L3.fusion.arousal', 'classifier.binary_rem', etc.
  meta_context    text,                       -- 'waking/focused', 'sleep/rem', etc. — denormalized for fast filter
  i_model_id      uuid NULL,                  -- commitment #1
  created_at      timestamptz DEFAULT now()
);
CREATE INDEX ON user_state_estimate(user_id, axis, timestamp DESC);
CREATE INDEX ON user_state_estimate(user_id, timestamp DESC) WHERE axis = 'meta_context';
```

**Backward compat:** existing wide-row rows (sleep classifier output) are migrated to per-axis-rows in the same transaction. One row in → up to N rows out, one per non-NULL axis.

### 6b. New table: `prediction_log`

Records every Regis discrete-action choice for #13 outcome-driven learning:

```sql
prediction_log(
  id                     uuid PRIMARY KEY,
  user_id                uuid NOT NULL,
  ts                     timestamptz NOT NULL,
  action_type            text NOT NULL,       -- 'interject', 'no_interject', 'chat_response'
  action_kind            text,                -- 'witness' / 'companion' / 'check_in' / etc.
  state_before           jsonb NOT NULL,      -- snapshot of relevant axes
  expected_state_after   jsonb,               -- L4 predictor's forecast (naive in v1)
  observed_state_after   jsonb,               -- filled by reconciler 5-15min later
  user_response_label    text,                -- 'accepted' / 'rejected' / 'ignored' / 'unknown'
  user_response_signal   jsonb,               -- raw signal (next-utterance prosody, HR delta, etc.)
  i_model_id             uuid NULL,
  created_at             timestamptz DEFAULT now()
);
CREATE INDEX ON prediction_log(user_id, ts DESC);
CREATE INDEX ON prediction_log(user_id, action_type, ts DESC);
```

### 6c. Consent metadata columns

Add to `sensor_readings`:
```sql
ALTER TABLE sensor_readings ADD COLUMN consent_scope text;
-- e.g., 'mic_continuous_v1', 'cam_continuous_v1' — indexes consent record at write time
ALTER TABLE sensor_readings ADD COLUMN suppressed_for jsonb;
-- e.g., {"reason": "other_voice_present", "window_start": "..."} — when pipeline paused but row still landed
```

### 6d. Canonical HealthKit storage path (post-0009 writer convention)

**Single canonical store.** All Apple Health data lands in `sensor_readings` under the `apple_health_*` kind namespace, written exclusively by `bin/sync_hk_export.py`:

| Kind | HealthKit type | Payload |
|------|----------------|---------|
| `apple_health_hr` | `HKQuantityTypeIdentifierHeartRate` | `{value, unit, source}` |
| `apple_health_hrv` | `HKQuantityTypeIdentifierHeartRateVariabilitySDNN` | `{value, unit, source}` |
| `apple_health_spo2` | `HKQuantityTypeIdentifierOxygenSaturation` | `{value, unit, source}` |
| `apple_health_respiratory_rate` | `HKQuantityTypeIdentifierRespiratoryRate` | `{value, unit, source}` |
| `apple_health_temperature` | `HKQuantityTypeIdentifierBodyTemperature` | `{value, unit, source}` |
| `apple_health_sleep_stage` | `HKCategoryTypeIdentifierSleepAnalysis` | `{stage, end, source, duration_s}` |

**Deprecated path.** `apps/inference/parse_apple_health.py` (the v0 bulk importer that wrote legacy bare kinds `heart_rate`/`hrv`/etc. and populated `sleep_sessions` + `sleep_stage_classifications`) is disabled by a hard guard and kept for history only. Do not re-run it.

**Frozen legacy.** `sleep_sessions` (76 rows) and `sleep_stage_classifications` (7338 rows) are the classifier's training corpus: read-only, never re-written, never re-imported, never re-pointed. They are NOT the live HealthKit store — the live store is `sensor_readings.apple_health_*`.

**Consent.** Every HealthKit write carries `consent_scope = 'apple_health_v1'`; every Mac-activity write carries `consent_scope = 'mac_activity_v1'` (see `apps/inference/consent.py`, privacy policy #1). `suppressed_for` stays NULL until the Week-3 privacy gate lands.

---

## 7. File structure (MVP target)

> **Realigned 2026-05-28 (post-scrap reality).** The original tree below assumed an
> `apps/chat/` package and `apps/inference/retrieval/substrate.py`. Neither survived the
> rebuild scrap. The conversational turn engine is now **`apps/wisp/composer.py`**
> (`compose_utterance()`), and the substrate seam lives inside it as
> `gather_substrate()` (currently a stub). Week 2 therefore builds a thin
> **`apps/voice/`** runtime that orchestrates wake-word → STT → `compose_utterance()`
> → TTS, rather than a separate chat handler. ARCHITECTURE.md is updated as these land.

```
apps/
├── recall/                          KEPT — validation wedge
├── wisp/                            KEPT — IS the turn engine
│   ├── composer.py                  — compose_utterance(): reads BeliefState + substrate, calls LLM
│   ├── gather_substrate()           — substrate seam (in composer.py); stub → real impl in Week 2
│   └── PERSONA.md
├── voice/                           NEW (Week 2) — waking-empath runtime loop
│   ├── loop.py                      — wake-word → STT → compose_utterance() → TTS orchestrator
│   ├── cli.py                       — run the loop (python -m voice.cli)
│   └── smoke_test.py                — end-to-end loop smoke (mockable mic/TTS)
├── api/                             KEPT + minor additions
│   └── routes/state.py              — /body, /body/series (canonical apple_health_* reads)
├── pi/                              OUT OF SCOPE (separate Pi chat owns migration)
└── inference/
    ├── db.py, consent.py, parse_apple_health.py (DEPRECATED), embeddings/, llm/   KEPT
    ├── llm/                          KEPT + RE-PULLED STT
    │   ├── chat.py                  — ChatClient.auto() (KEPT)
    │   ├── stt.py                   — RE-PULLED: file/record transcription (uses recall.whisper_client)
    │   └── stt_streaming.py         — RE-PULLED: transcribe_streaming() mic → text
    ├── classifier/                   KEPT (model is the asset)
    ├── audio/                        RE-PULLED from v0-pre-rebuild tag (TTS, L6)
    │   ├── kokoro_tts.py             — high-quality local TTS
    │   ├── say_tts.py                — macOS `say` fallback (zero-dep, ships first)
    │   ├── tts_router.py            — synthesize()/speak(), picks backend, witness/companion modes
    │   ├── streaming.py             — speak_streaming() sentence-chunked playback
    │   └── player.py                — sounddevice playback
    ├── wake_word/                    RE-PULLED (detector + intent only; handlers deferred)
    │   ├── detector.py              — VoiceWakeWordDetector (openWakeWord wrapper)
    │   ├── command_intent.py        — classify_intent() (stop/dismiss vs message routing)
    │   └── training/README.md       — "Hey Regis" custom-model training paths
    ├── migrations/                   0009 + 0010 APPLIED
    ├── capture/                      L1 — watch + mac_sensors KEPT (Week 1)
    ├── features/                     L2 — snapshot.py (FeatureSnapshot, has `intent`) KEPT
    ├── fusion/                       L3 — KEPT (Week 1)
    │   ├── belief_state.py          — BeliefState + AxisEstimate (freshness gates)
    │   ├── loader.py                — NEW (Week 2): load_belief_state(user_id) from DB rows
    │   ├── writer.py                — per-axis-row writer
    │   └── axes/{meta_context,sleep_stage}.py
    ├── prediction/                   NEW (L4) — deferred (F8: lands when L4 starts)
    └── decision/                     NEW (L5) — Week 4

bin/
├── cloudflare-tunnel-{setup,run}.sh  KEPT
└── sync_hk_export.py                 KEPT — canonical Apple Health pull (6 apple_health_* kinds)
```

> `apps/inference/wake_word/handlers.py` is intentionally **not** re-pulled in Week 2:
> it imports `gesture.recorder`, which the scrap removed. Command-side actions
> (LISTEN/SEE/DISMISS → DB) return when the gesture layer is rebuilt. Week 2 only
> needs `classify_intent()` to distinguish a "stop"/"dismiss" command from a real
> message routed to the composer.

---

## 8. Week-by-week milestones with exit criteria

### Week 1: Schema + watch + Mac sensors → first two axes lit

**Goal:** Per-axis-row schema lands. Apple Health flows in. Mac sensors writing. `meta_context` + `sleep_stage` populating.

Exit criteria:
- [ ] Migration 0009 applied to Neon (via `mcp__Neon__prepare_database_migration` → review → `complete_database_migration`)
- [ ] Existing wide-row data successfully migrated to per-axis-rows (verify count + sample)
- [ ] `bin/sync_hk_export.py` pulls last 24h of Apple Health into `sensor_readings`, idempotent
- [ ] `apps/inference/capture/mac_sensors.py` writes `active_app` + `keystrokes_per_min` every 30s
- [ ] `apps/inference/fusion/belief_state.py` reads `sensor_readings`, computes `meta_context` + `sleep_stage`, writes per-axis-row
- [ ] `python -m fusion.smoke_test` passes (asserts axes populated from real data, freshness policy works)
- [ ] STATUS.md updated, REBUILD_PLAN.md week-1 checked off
- [ ] Tag `mvp-week-1-end`

### Week 2: Voice loop restored, but state-aware

**Goal:** Wake-word → STT → `compose_utterance()` → TTS path works, with the composer reading the freshness-gated BeliefState before generating. (Realigned 2026-05-28: turn engine is the composer, not a separate `apps/chat/handler.py`; orchestration lives in new `apps/voice/`.)

Exit criteria:
- [ ] `apps/inference/audio/` re-pulled from `v0-pre-rebuild` tag; `python -m audio.smoke_test` passes (macOS `say` backend at minimum)
- [ ] `apps/inference/llm/stt.py` + `stt_streaming.py` re-pulled; import-clean against current `recall.whisper_client`
- [ ] `apps/inference/wake_word/` re-pulled (detector + command_intent only; handlers deferred — needs `gesture/`); `python -m wake_word.smoke_test` passes
- [ ] TTS/STT/wake-word deps added to `apps/inference/pyproject.toml`; install verified
- [ ] `fusion/loader.py::load_belief_state(user_id) -> BeliefState` reads latest per-axis `user_state_estimate` rows, wraps each as `AxisEstimate` (freshness applied)
- [ ] `compose_utterance()` reads state via `load_belief_state(...).snapshot()` (freshness-gated) instead of raw `_read_latest_state`
- [ ] `wisp/composer.py::gather_substrate()` stub replaced with a real impl returning observations + traits + current state
- [ ] OpenWakeWord "Regis" custom model trained (Colab/local per `wake_word/training/README.md`), dropped at `wake_word/models/hey_regis.onnx`; placeholder `hey_jarvis` works until then
- [ ] `apps/voice/loop.py` orchestrates: wake-word fires → `transcribe_streaming()` → `classify_intent()` (stop/dismiss vs message) → `compose_utterance()` → `tts_router.speak()` (mode from `ComposedUtterance.mode`)
- [ ] `python -m voice.smoke_test` passes with mockable mic/TTS (no hardware needed in CI)
- [ ] End-to-end manual: utter "Regis, how am I?" at a moment of inferred focus → Regis's spoken response is shaped by that state (verified by inspecting the assembled LLM prompt + word choice)
- [ ] ARCHITECTURE.md updated (voice loop + composer-as-engine), STATUS.md updated
- [ ] Tag `mvp-week-2-end`

### Week 3: Continuous mic semantic pipeline + EEG stretch

**Goal:** Mic doesn't just listen for wake-word — it produces semantic packets continuously. (Stretch) EEG feeding cognitive_load axis.

**Realigned 2026-05-28 (post-Week-2).** Core building blocks are re-pullable from `v0-pre-rebuild` `apps/inference/audio_context/` (`vad.py` Silero, `diarization.py` resemblyzer+sklearn clustering, `prosody.py` librosa, `processor.py`, `persistor.py`) — but the tag does UNSUPERVISED clustering ("speaker 0/1"), persists one flat `audio_segment` kind, and has no `consent_scope`. Week 3 adds: speaker *identity* (enroll Aakash → classify), a differentiated packet taxonomy, the Privacy Policy #1 state machine, the `audio_social_context` axis, YAMNet ambient, and folds continuous listening into ONE unified always-on mic loop in `apps/voice/loop.py` (shared with the Week 2 wake-word path — no two-process mic contention). Deps: `silero-vad`, `resemblyzer`, `librosa` (new); `torch`, `scikit-learn` (present); `tensorflow-hub`+`tensorflow` for YAMNet, isolated as a lazy backend so its import can't break the core pipeline.

Packet taxonomy (`sensor_readings`, `consent_scope="mic_continuous_v1"`):
- `audio_social_context` — `{speaker: "aakash"|"other"|"both"|"none", num_speakers, vad_active}`, written at speech/silence transitions. Drives the axis.
- `audio_prosody` — `{energy, pitch_mean_hz, pitch_std_hz, tone}`, Aakash-only (privacy-gated).
- `audio_ambient` — `{top_classes, scores}`, YAMNet, every 5s during silence (privacy-gated).

Exit criteria:
- [ ] `apps/inference/audio_context/` re-pulled (vad/diarization/prosody/processor/persistor); deps added + installed; `python -m audio_context.smoke_test` passes
- [ ] `apps/inference/audio_context/speaker_id.py` — `enroll(user_id, wav_paths)` (resemblyzer centroid → persisted) + `identify(embedding) -> "aakash"|"other"` (cosine threshold); Aakash enrolled from reference clips
- [ ] `persistor`/`processor` updated to the differentiated packet taxonomy above + `consent_scope`; `CONSENT_SCOPES["mic"]="mic_continuous_v1"` added to `consent.py`
- [ ] Privacy Policy #1 enforced (locked §5): non-Aakash voice → write only `audio_social_context` `{speaker:"other"/"both"}`; suppress prosody + ambient + STT for that window + 30s silence buffer. Unit-tested state machine.
- [ ] `apps/inference/audio_context/ambient.py` — YAMNet behind a lazy backend (`classify_ambient(audio, sr) -> list[{class, score}]`), graceful "unavailable" fallback
- [ ] `apps/inference/fusion/axes/audio_social_context.py` — reads recent `audio_social_context` packets → `AxisEstimate` (alone/with_other); arousal_inferred lightly refined from prosody tone
- [ ] `apps/voice/loop.py` — ONE always-on mic loop: each block feeds wake-word detection AND a rolling VAD buffer; on speech-segment end → identify → privacy gate → social/prosody packets; during silence → ambient every 5s; wake-word fire → existing `run_turn`. Hardware-free smoke with injected audio.
- [ ] STRETCH: BioAmp wired (Pi or direct-USB), `apps/inference/capture/eeg.py` writes alpha/beta/theta packets at 1Hz, `cognitive_load` axis lit
- [ ] ARCHITECTURE.md + STATUS.md updated; theory-aligner pass (standing rule)
- [ ] Tag `mvp-week-3-end`

### Week 4: Decision layer + outcome logging + Friday-review query

**Goal:** Regis can decide to interject (when policy permits), every action logs outcome, "how was the week?" produces trajectory-grounded answer.

Exit criteria:
- [ ] `apps/inference/decision/policy.py` fixed-weight rules implemented (interject-vs-not, witness-vs-companion); MVP default leans toward not-interject (rough heuristic: only interject if session_duration > 2h + last_break > 45min + state_declared mentions tiredness)
- [ ] Every Regis action (chat response, interject, no-interject choice) writes a `prediction_log` row
- [ ] Reconciler job runs every 15min: backfills `observed_state_after` and `user_response_label` based on subsequent state + chat turns
- [ ] `python -m chat.cli` → "Regis, how did this week feel?" produces an answer that references per-axis trajectories (verified by reading the assembled prompt)
- [ ] Reflection: 1-page note in `docs/sessions/` on what worked, what didn't, week-5 adjustments
- [ ] STATUS.md + REBUILD_PLAN.md updated
- [ ] Tag `mvp-week-4-end`

### Week 5: Polish + slack

Buffer for whatever slipped. If on track:
- [ ] Live with the MVP for 5+ days. Validation wedge clock starts: ≥50% dream recall improvement vs 14-day pre-baseline.
- [ ] One demo loop captured (transcript or audio) for sharing
- [ ] **Architectural commitments audit:** re-read all 16 against the as-shipped MVP. Update auto-memory `project_daybook.md` with any drift or refined understanding.
- [ ] Re-evaluate privacy Policy #1 — promote to #2 if data loss is significant
- [ ] Tag `mvp-v1-end`. Plan v1.5 from learned ground truth.

---

## 9. Out-of-scope, deferred to v1.5+

- **Cam pipeline** (visual semantic packets — YOLOv8n + MediaPipe stack)
- **iPhone sensors** (no iOS client until v1.5)
- **I-Model self-expansion (#6)** — clusters stay seeded
- **JEPA world model implementation (#16)** — interface scaffolded, encoder/predictor/SIGReg/CEM training deferred to v2 once data accumulates
- **Causal reasoning (#15)** — `action` param preserved at L4 interface, but action-conditioning is naive placeholder
- **Interject without summon** — Policy gated to "not" in v1; bandit unlocks this in post-MVP
- **BCI beyond single-channel EEG** — wearable form factor is v3+
- **Multi-user, clinical integrations, web app** — all v2+
- **Pi-side migration to L1/L2/L6 boundaries** — owned by separate Pi chat, runs in parallel; this spec does not block on it

---

## 10. Risks + mitigations

1. **BioAmp ships day 2; EEG capture wiring slips.** → EEG stays stretch. Week 3 still ships continuous-audio without EEG.
2. **OpenWakeWord "Regis" model quality.** Custom wake-word accuracy varies. Fallback: use a built-in OWW word ("hey jarvis") and accept brand mismatch through MVP.
3. **Pi chat coordination delay.** If BioAmp EEG must route via Pi → Mac, and Pi chat hasn't migrated, route EEG direct USB-serial to Mac for MVP.
4. **Privacy Policy #1 too aggressive.** If Aakash works alone almost always, the conservative default silently drops data. Mitigation: weekly review of `suppressed_for` rows; promote to Policy #2 if data loss is meaningful.
5. **`prediction_log` cold-start.** Bandit can't learn until ~50+ outcomes labeled. Fixed-weight policy must be defensible from day 1. Mitigation: policy.py rules are based on observable heuristics, not learned weights, so cold-start is fine.
6. **Schema migration risk.** The wide-row → per-axis-row reshape is the riskiest move. Mitigation: PR + smoke test that asserts row counts match, plus the Neon branch snapshot lets us roll back the *data* if the migration corrupts.
7. **Scope creep into v1.5 territory.** Saying "I'll just add cam this week" is the failure mode. Mitigation: every scope expansion must update this spec first, with explicit deferral of equivalent depth elsewhere.

---

## 11. Success: what "MVP shipped" feels like

Day 30-45. Watch on wrist. EXG headband on (or off — the system degrades gracefully). External mic listening. Mac tracking active windows. The Contextual Map updates silently every 30 seconds across 4-5 axes.

You say *"Regis, what's the day looked like?"* — OpenWakeWord catches "Regis", `stt_streaming` captures the rest, chat handler reads the current BeliefState, `retrieval/substrate.py` pulls relevant past observations + recent prosody trajectory + state_declared mentions from the morning. Composer assembles all that into a Codex call. Regis answers via TTS through your bone-conduction headphones — three sentences naming the actual shape of your day, not from your self-report, from your physiology and the things you said hours ago.

She doesn't tell you "you were focused." She says something like:

> *"You started slow — HRV took until ten-thirty to settle. The block before lunch was the steadiest stretch this week. You came back tired at one and never quite landed. Walk."*

That's the MVP. The schema, layers, and policies are in place to grow this into the full waking empath + dream observer + clinical extension + wearable arc over the next year.

---

## 12. How this spec stays alive

- **Updated when scope shifts.** Any commitment-depth change or sensor-phasing change edits this file *first*, with explicit deferral elsewhere to keep total scope constant.
- **Referenced from REBUILD_PLAN.md** — the plan phases align to the weeks here.
- **Referenced from STATUS.md** at week boundaries.
- **Audited at MVP end** (week 5) for drift vs as-shipped reality. The audit lands in `docs/sessions/`.

---

*Spec written 2026-05-27. Awaiting review before transition to writing-plans skill.*
