# Daybook — Big Picture Status

**Last updated: 2026-05-17 (Pi daemon built + smoke-tested; Pi-side hardware foundation complete; Regis architecture + three I-Models committed)**

The single page that answers "where are we, where are we going, what's blocking us?" Updated after substantive work lands. Open this any session when you need orientation.

---

## North star

**Koine Labs:** *Build the infrastructure of two worlds — the world awake and the world asleep — and the interface that makes them one.*

**Daybook v1 (the first product):** A personal cognitive companion that intervenes at the right sleep moments to improve **dream recall frequency** by ≥50% vs a 14-day baseline. User-facing presence is **Regis**, a will-o-wisp character living in bone-conduction audio. Bedside-first prototype; iOS app deferred to months 4-6.

**v1 success criterion (locked):** ≥50% relative improvement in weekly dream recall vs 14-day pre-baseline. Single-subject (Aakash) for 60-90 days.

**Capital posture:** Bootstrapped. ~$60-70 spent on incremental hardware. Free tiers everywhere possible.

---

## Three parallel tracks

The whole product is the intersection of these three. They run in parallel because they have independent dependencies. All three must function for v1 to be real.

### Track 1 — Bedside hardware lab

The physical sensing rig that runs at Aakash's bedside. Pi 4 brain, ESP32 satellites, EEG + bone-conduction.

| State | What |
|---|---|
| [HAVE] | Pi 4 (flashed, SSH'd in from Mac), ESP32 (MicroPython flashed, REPL via Pi USB), 2× ESP32-CAM, Arduino Uno, 3.5" TFT, 3D printer, lasers, 24/7 PC, MacBook, Apple Watch S8/9 |
| [ORDERED — arriving ~10 days] | BioAmp EXG Pill ($35, Tindie) — single-channel biopotential amplifier for EEG/EMG/ECG |
| [ORDERED — arriving ~2-3 days] | TECKNET bone-conduction headphones (~$25-30, Amazon) |
| [DONE — 2026-05-17] | Pi OS Lite 64-bit flashed (PC-side after Mac-Imager flake), SSH-by-key from Mac via `daybook` alias, koine-labs user, apt updates done, repo cloned to `~/code/daybook` |
| [DONE — 2026-05-17] | ESP32 (CP210x) on Pi USB at `/dev/ttyUSB0`, MicroPython v1.28.0 flashed, REPL via mpremote, GPIO commands echo cleanly |
| [DONE — 2026-05-17] | **Pi daemon at `apps/pi/`** — sensor-source-pluggable (mock + esp32_serial + future cam/mic), cue-emitter-pluggable (stdout + future audio/haptic), wires to AI-side `RealtimeClassifier` + `CueDecider`, persists sensor_readings/cue_events/user_state_estimate to Neon. Smoke-tested end-to-end (2-min mock run, clean shutdown, all DB writes verified then cleaned up). |
| [ORDERED — arriving ~2 days] | ESP32-CAM-MB programmer adapter board (FT232-based, plug-and-play for AI-Thinker CAM) |
| [QUEUED] | ESP32 firmware for sensor packet emission (JSON-line over serial per AI_PI_CONTRACT.md), EXG Pill electrode placement, bench tests (EMG forearm → ECG chest → EEG scalp), TFT display bring-up (Pi HAT), ESP32-CAM as "eyes for the AI" multi-modal source |

**Interface to AI:** `apps/AI_PI_CONTRACT.md` documents the API the Pi daemon imports from `apps/inference/`. Lock-step versioned.

### Track 2 — Wisp interface (Regis)

The character + voice + audio routing. The interface layer of the product.

| State | What |
|---|---|
| [DECIDED] | Persona = Regis (TBATE-inspired will-o-wisp). Bone-conduction audio delivery. v1 = scripted utterance moments; v2+ = generative conversational. |
| [DONE — 2026-05-17] | **`apps/wisp/PERSONA.md`** — character bible, **dual-mode Regis** (Witness Mode during sleep / Companion Mode awake), canon-grounded snark + logo-grounded softness, vocabulary discipline, 10 v1 utterance slots with starter variants |
| [DONE — 2026-05-17] | **Logo finalized:** `/Logo/Clear-Koine-Wisp.png` — small luminous wisp, warm amber glow, soft horns. This is Witness-Mode Regis visualized. |
| [NOT DECIDED] | TTS provider (ElevenLabs / Cartesia / OpenAI Voice / Sesame). Voice character / accent. |
| [NOT BUILT] | TTS wrapper (`apps/pi/tts.py`), utterance variant selector, bone-conduction routing pipeline, audio output testing |

**Blocker:** Bone-conduction headphones not yet arrived. TTS provider not yet picked.

### Track 3 — Backend infrastructure (data + models)

The intelligence layer. Where sensor data becomes stage predictions becomes cue decisions.

| State | What |
|---|---|
| [DONE — 2026-05-17] | Postgres schema deployed to Neon (11 tables, pgvector HNSW index, indexes) |
| [DONE — 2026-05-17] | Apple Health XML parser — imported 495K sensor readings, 543 sleep sessions, 7,568 stage classifications from 10-year HK export |
| [DONE — 2026-05-17] | TypeScript shared types (`packages/shared/`), branded ID system, Python DB helper |
| [DONE — 2026-05-17] | **Sleep-stage classifier pipeline** — data loader, feature extraction (24-29 features per 30s epoch), naive baselines, LOSO XGBoost training, evaluation, exploration notebook |
| [DONE — 2026-05-17] | **Full LOSO baseline trained.** 249 sessions, 204K epochs. V2 pure-bio model: F1 = 0.45, ROC-AUC = 0.72. Honest floor established. |
| [DONE — 2026-05-17] | **Production binary REM model trained** on all 249 sessions (no holdout). Saved to `classifier/models/production_binary_rem.json` + sidecar metadata. |
| [DONE — 2026-05-17] | **`apps/inference/realtime.py`** — `RealtimeClassifier` with rolling sensor buffers + per-epoch features matching offline pipeline. Smoke-tested on real session. |
| [DONE — 2026-05-17] | **`apps/inference/cue_decision.py`** — `CueDecider` with safety gates: 60-min ramp-up, 30-min end-zone, 25-min cooldown, confidence floor, max-cues. Smoke-tested. |
| [DONE — 2026-05-17] | **End-to-end smoke test on real session:** both fired cues landed INSIDE Apple-labeled REM segments. No false positives. (Recall limited by conservative gates — by design for v0.) |
| [DONE — 2026-05-17] | **Migration 0002 applied to Neon:** `regis_observations`, `regis_trait_history`, `user_state_estimate` tables. `i_model_clusters.model_owner` extended (user_self / regis_of_user / regis_self). TypeScript types mirrored. |
| [DONE — 2026-05-17] | **`RealtimeClassifier.predict_at` writes to `user_state_estimate`** when `persist_state=True`. Empathic time series builds passively from v1 onward. Smoke-tested. |
| [NOT BUILT] | Live sensor ingestion HTTP endpoint, embeddings pipeline for dream content, generative wisp utterance composer (v2+), regis_observer job (v1.5 — writes regis_observations after each session), regis trait-drift logic (v2) |

**No external blocker** for the next backend work; the question is sequencing.

---

## What this session's work was

**Tracks 2 + 3 in parallel** (with Track 1 happening in a separate chat on the Pi).

**Track 3 — AI brain that the Pi will import:**
- Trained the production binary REM model on all 249 sessions (pure-bio, 24 features)
- Built `RealtimeClassifier` (live inference with rolling sensor buffers)
- Built `CueDecider` (stateful, 5 safety gates: ramp-up / end-zone / cooldown / confidence floor / consecutive-high requirement)
- End-to-end smoke test on a real 6.9h session — both fired cues landed inside Apple-labeled REM segments

**Track 2 — Regis character spec (now dual-mode + canon-grounded):**
- `apps/wisp/PERSONA.md` — rewrote after looking up canonical TBATE Regis and the finalized logo. **Two modes:** Witness (reverent, sparse, during sleep) + Companion (dry, teasing, when user is awake). Honors canon snark in waking moments, logo softness in vulnerable moments.

**Architecture commitment — three I-Models:**
- Added migration 0002. We now have schema for: (1) **user-self** (what we know about you, already there), (2) **regis-of-user** (what Regis has noticed about you), (3) **regis-self** (Regis's evolving personality dials).
- `user_state_estimate` now builds passively from every `RealtimeClassifier.predict_at()` call. This is the empathic substrate — Regis "reads" the user without explicit conversation by querying this table.

**Interface contract:**
- `apps/AI_PI_CONTRACT.md` — the stable target the Pi daemon builds against

---

## Gaps preventing v1

In rough order of blocking severity:

1. **No EEG data.** Hardware in transit. ~10 days out.
2. **No live sensor capture path.** ESP32 firmware → Pi daemon → Postgres pipeline. Pi-chat working on Pi side now; ESP32 firmware not yet started.
3. **No TTS pick + audio routing.** Persona is written; need a voice + a synthesis layer + bone-conduction routing. Blocked on bone-conduction arrival.
4. **No dream-recall measurement habit yet.** Aakash hasn't started the 14-day pre-baseline journal (this is the success metric — without it, v1 has no ground truth to improve against).
5. **No CLAUDE.md rewrite.** The repo's CLAUDE.md still has the old Lullaby narrative; needs to reflect Daybook v1 thesis. Not blocking but creates confusion.

---

## Next milestones (rough, no committed dates)

1. **Bone-conduction arrives** → Track 2 begins. First wisp test = play a scripted line through the speaker while Aakash is awake. Confirm audio routing works.
2. **BioAmp Pill arrives** → Track 1 bench tests (EMG forearm → ECG chest → EEG scalp). Validate signal quality before scalp placement.
3. **EEG signal validated** → first ESP32 sensor capture firmware → Pi ingestion → live Postgres writes.
4. **Live ingestion works** → real-time inference service spun up (Python FastAPI). Classifier now runs on live windows, not just historical.
5. **End-to-end loop runs once on Aakash** → bedside sensor → live inference → wisp utterance fires when REM detected.
6. **Dream-recall baseline started** (Aakash's habit, no code) → 14 morning entries needed for v1 to have a comparison point.
7. **N=1 study (60-90 days)** → does the loop improve recall by ≥50% vs baseline?
8. **v1 ships** if the data supports it.

---

## What's true *right now*, in three sentences

- **All three tracks are now actively moving.** Track 1 = Aakash on Pi in a separate chat. Track 2 = Regis persona written. Track 3 = realtime inference + cue decider built and validated on real data.
- **The next concrete integration milestone** is the Pi daemon importing `apps/inference/realtime.py` + `cue_decision.py` and running a synthetic session end-to-end. That happens whenever Pi-side is ready.
- **The highest-leverage non-engineering thing** is still starting the 14-day dream-recall baseline journal. Without that data, v1 has no measurable claim to make.

---

## Canonical references (read these for depth)

- **`docs/POSITIONING.md`** — full strategic anchor (customer, problem, solution, competitive analysis, defensibility, expansion path)
- **`apps/inference/classifier/runs/20260517_v2_pure_bio/`** — recommended classifier model
- **`apps/inference/classifier/runs/20260517_033114/RESULTS.md`** — original full LOSO writeup
- **`MIGRATION.md`** — what was kept vs scrapped from Lullaby
- **`docs/sessions/`** — historical session logs (decisions captured in numbered form)

---

## How to keep this doc useful

Update after substantive work lands. Don't update for trivial things. A good update either changes a `[NOT BUILT]` → `[DONE]`, moves a blocker forward, or revises a milestone. Date the change at the top.
