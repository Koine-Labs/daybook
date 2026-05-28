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

---

## 7. File structure (MVP target)

```
apps/
├── recall/                          KEPT — validation wedge
├── wisp/                            KEPT — composer.py + PERSONA.md
├── chat/                            REBUILT LIGHTER
│   ├── handler.py                   — turn handler reading BeliefState before compose
│   ├── conversation.py              — lifecycle (start/append/end)
│   └── cli.py                       — REPL surface
├── api/                             KEPT + minor additions
│   └── routes/state_timeline.py     — NEW: GET /state/timeline?axis=&from=&to=
├── pi/                              OUT OF SCOPE (separate Pi chat owns migration)
└── inference/
    ├── db.py, parse_apple_health.py, embeddings/, llm/   KEPT
    ├── classifier/                   KEPT (model is the asset)
    │   └── inference.py              — NEW: thin wrapper loading production_binary_rem.json
    ├── audio/                        RE-PULLED from v0-pre-rebuild tag
    │   ├── kokoro_tts.py             — high-quality local TTS
    │   ├── say_tts.py                — macOS `say` fallback
    │   └── tts_router.py             — picks backend
    ├── migrations/
    │   └── 0009_per_axis_state_and_prediction_log.sql   NEW
    ├── capture/                      NEW (L1)
    │   ├── watch.py                  — Apple Health export → sensor_readings writer
    │   ├── mac_sensors.py            — AppleScript active-app + keystrokes-per-min
    │   ├── eeg.py                    — BioAmp serial reader (stretch)
    │   ├── mic_wakeword.py           — OpenWakeWord listener
    │   └── mic_continuous.py         — VAD + diarization + prosody + ambient
    ├── features/                     NEW (L2)
    │   ├── snapshot.py               — FeatureSnapshot envelope (uniform shape)
    │   ├── biometric.py              — HR/HRV/motion → per-epoch features
    │   ├── audio.py                  — prosody → features
    │   └── mac.py                    — Mac sensor features
    ├── fusion/                       NEW (L3)
    │   ├── belief_state.py           — BeliefState dataclass, freshness policy
    │   ├── writer.py                 — per-axis-row writer to user_state_estimate
    │   └── axes/
    │       ├── arousal.py
    │       ├── meta_context.py
    │       ├── sleep_stage.py
    │       ├── state_declared.py
    │       └── audio_social_context.py
    ├── prediction/                   NEW (L4)
    │   ├── base.py                   — Predictor interface: predict(axis, horizon, action)
    │   └── per-axis stubs            — naive regression scaffolds, JEPA-shaped interface
    ├── decision/                     NEW (L5) — REPLACES deleted interject + cue_decision
    │   ├── policy.py                 — fixed-weight rules (interject?, witness vs companion?)
    │   └── outcome_logger.py         — writes prediction_log rows + reconciler
    └── retrieval/                    NEW (L4+L5 memory) — REPLACES deleted imodels.substrate
        └── substrate.py              — gather_substrate() returns context for composer

bin/
├── cloudflare-tunnel-{setup,run}.sh  KEPT
└── sync_hk_export.py                 NEW — cron-able Apple Health pull
```

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

**Goal:** Wake-word → STT → chat → TTS path works, with composer reading BeliefState before generating.

Exit criteria:
- [ ] `apps/inference/audio/` re-pulled from `v0-pre-rebuild` tag (`git checkout v0-pre-rebuild -- apps/inference/audio/`); smoke tests pass
- [ ] OpenWakeWord "Regis" custom model trained (via their TTS-augmentation pipeline), listening on external mic
- [ ] Wake-word fires → `llm/stt_streaming.transcribe_streaming()` → chat handler (rebuilt lighter in `apps/chat/handler.py`)
- [ ] Chat handler reads current BeliefState before calling composer
- [ ] Composer reads from `apps/inference/retrieval/substrate.py` (stub replaced with real impl returning context)
- [ ] Regis's response spoken via TTS through bone-conduction
- [ ] End-to-end smoke: utter "Regis, how am I?" at a moment of inferred focus → Regis's response is shaped by that state (verified by inspecting the LLM prompt and Regis's word choice)
- [ ] STATUS.md + REBUILD_PLAN.md updated
- [ ] Tag `mvp-week-2-end`

### Week 3: Continuous mic semantic pipeline + EEG stretch

**Goal:** Mic doesn't just listen for wake-word — it produces semantic packets continuously. (Stretch) EEG feeding cognitive_load axis.

Exit criteria:
- [ ] Silero VAD running on mic stream, writes social_context packets at speech/silence transitions
- [ ] Speaker embedding enrolled for Aakash; per-utterance speaker classification
- [ ] librosa prosody (F0, energy, speaking_rate) extracted on Aakash-only speech, written as `audio_semantic` packets
- [ ] YAMNet ambient classifier running every 5s during silence
- [ ] `audio_social_context` axis lit in `fusion/axes/`
- [ ] Privacy Policy #1 enforced: non-Aakash voice → 30s pause + silence buffer on prosody + ambient
- [ ] STRETCH: BioAmp wired (Pi or direct-USB), `apps/inference/capture/eeg.py` writes alpha/beta/theta packets at 1Hz, `cognitive_load` axis lit
- [ ] STATUS.md + REBUILD_PLAN.md updated
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
