# Daybook — Big Picture Status

**Last updated: 2026-05-28 — MVP Week 3 (continuous-mic semantic pipeline) implemented.**

## 2026-05-28 — MVP Week 3: continuous-mic semantic pipeline

**Shipped (branch `feat/week-3-continuous-mic`):**
- Re-pulled from `v0-pre-rebuild`: `apps/inference/audio_context/` (VAD via silero, diarization + prosody via resemblyzer/librosa). New base deps: `silero-vad`, `resemblyzer`, `librosa`. YAMNet (`tensorflow`/`-hub`) is an **optional** dep group, never in the base install.
- `audio_context/speaker_id.py` — enroll a voice centroid from reference clips; `identify()` returns `self` / `other` / `unknown` by cosine similarity (threshold 0.75).
- `audio_context/writer.py` — three differentiated `sensor_readings` packet kinds (`audio_social_context`, `audio_prosody`, `audio_ambient`), each stamped `consent_scope=mic_continuous_v1`. SQL verified live (insert→readback→delete).
- `audio_context/privacy.py` — **Privacy Policy #1** as a pure, unit-tested state machine: non-self voice → presence marker only + suppress prosody/ambient/STT for the window **+ 30s buffer**. `unknown` speaker fails safe to `other`.
- `audio_context/ambient.py` — YAMNet ambient classifier behind a lazy, fail-soft backend (returns `[]` when TF absent); clip-level `mean(axis=0)` reduction.
- `fusion/axes/audio_social_context.py` — L3 axis (`alone` / `with_other`). **Three L3 axes now live** (`meta_context`, `sleep_stage`, `audio_social_context`).
- `apps/voice/` — `ContinuousProcessor` (pure, injectable I/O) + `listen_continuous()`: ONE always-on mic stream does wake-word **and** privacy-gated continuous semantics (no second mic / no process contention). `run_turn`/`listen_forever` untouched. `cli.py --continuous`.
- **Verified:** 46 tests + voice/fusion smokes green; ambient fail-soft confirmed; writer SQL exercised against live Neon. Built via a parallel subagent workflow (5 modules + integration), each spec+quality reviewed, all review nits resolved by the orchestrator.

**Manual follow-ups (the unlocks):**
- **Enroll Aakash's voice** — record 3–5 clips → `audio_context.speaker_id.enroll(...)`. Until then `identify` returns `unknown` and the privacy gate conservatively suppresses prosody/ambient (fail-safe, but no rich signal yet).
- **Enable ambient** — `uv pip install ".[ambient]"` from `apps/inference`; until then the loop writes no `audio_ambient` packets.
- Window cadence (`window_seconds=3.0`) + `fresh_for_seconds` are first-guesses; tune once living with it. The 30s privacy buffer is the locked §5 value.
- EEG stretch deferred until the BioAmp EXG Pill is in hand.

**Next:** EEG axis (`cognitive_load`) when hardware lands; L4 prediction scaffolds; learned decider.

---

## 2026-05-28 — MVP Week 2: state-aware voice loop

**Shipped (branch `feat/week-2-voice-loop`):**
- Re-pulled from `v0-pre-rebuild`: `apps/inference/audio/` (TTS), `wake_word/` (detector + intent; `handlers.py` deferred — needs scrapped `gesture/`). STT (`llm/stt*.py`) already survived on main.
- New deps in `apps/inference/pyproject.toml`: `sounddevice`, `soundfile`, `faster-whisper`, `openwakeword`, `onnxruntime`. TTS ships on macOS `say` (kokoro optional); wake-word on built-in `hey_jarvis` until custom model trained.
- `apps/inference/fusion/loader.py::load_belief_state(user_id)` — DB per-axis rows → freshness-gated `BeliefState`.
- `apps/wisp/composer.py` — `_read_latest_state` now routes through `load_belief_state` (stale axes dropped, commitment #14); `gather_substrate()` stub replaced with real readers (observations + traits + current state).
- `apps/voice/` — new runtime: `run_turn()` orchestrates wake → STT → `classify_intent` → `compose_utterance` → `speak`; `listen_forever()` mic loop; `cli.py` (`--once/--text`); hardware-free `smoke_test.py`.
- **Verified end-to-end live:** `run_turn` with real composer produced a state-aware Companion-mode reply ("A little frayed, a little wired…"). 27 tests + voice/fusion/wake smokes green.

**One-time setup on a fresh venv:** `python -c "import openwakeword; openwakeword.utils.download_models()"` (detector does not auto-download base models).

**Known follow-ups (logged, not blocking):**
- `wake_word/command_intent.classify_intent` false-positives on short questions containing command keywords (e.g. "right" in "how am I right now?" → ACKNOWLEDGE). Harmless today (only DISMISS/SCRATCH_THAT short-circuit a turn); tighten in Week 3.
- Per-axis `fresh_for_seconds` likely needs tuning — Apple-Health-derived axes (hours old) gate out of the waking read by design; revisit when `meta_context` writes every 30s.
- "Hey Regis" custom wake model still to train (manual, `wake_word/training/README.md`).
- Freshness semantics: `belief_state.py` `is_fresh()` is Hide-only (drop stale) while `ARCHITECTURE.md §3 L3` describes a decay-default; reconcile one to the other (pre-existing Week-1 discrepancy, flagged by theory-aligner 2026-05-28).

**Next:** Week 3 — continuous mic semantic pipeline (VAD + diarization + prosody + ambient) + EEG stretch. Per spec §8.

---

## 2026-05-28 — MVP Week 1 complete

**Shipped this week (PRs #1–#8 on `main`):**
- Migration 0009: per-axis-row `user_state_estimate` + `prediction_log` + `sensor_readings` consent columns. Applied via Neon MCP; backfill verified.
- `bin/sync_hk_export.py` — incremental Apple Health → `sensor_readings`, idempotent.
- `apps/inference/capture/mac_sensors.py` — active_app + idle_seconds loop, 30s tick.
- `apps/inference/features/snapshot.py` — `FeatureSnapshot` L2 envelope.
- `apps/inference/fusion/` — `BeliefState` + per-axis writer + `meta_context` + `sleep_stage` axes.
- End-to-end smoke: `python -m fusion.smoke_test` writes per-axis rows from live Mac sensor + Apple Health data (`waking/browsing` confirmed in Neon).
- Fixed pre-existing `python-multipart` gap so the FastAPI bridge can start.

**Two L3 axes live:** `meta_context`, `sleep_stage`. Other axes (`arousal_inferred`, `state_declared`, `audio_social_context`, `cognitive_load`) defer to Weeks 2–3.

**What runs tonight:**
- `python -m recall.capture --text "..."` — dream-recall logging (writes `dream_recalls` + embedding).
- `apps/api/` FastAPI bridge — surviving routes: `health`, `recall`, `dreams`, `observations`, `sessions`, `persona`, `state`. Chat + compose routes deleted pending Phase 6/8 rebuild.
- `apps/wisp/composer.py` — LLM-composes from persona + explicit_context only; substrate (retrieval, traits, prosody, I-Models) returns in Phase 6.
- BGE-M3 embeddings + Codex LLM client (`apps/inference/{embeddings,llm}`) — fully functional.
- Trained sleep classifier model file (`apps/inference/classifier/models/production_binary_rem.json`) — preserved; not yet wired.
- **NEW:** `python -m capture.mac_sensors` (loops, writes `mac_activity` to `sensor_readings` every 30s).
- **NEW:** `bin/sync_hk_export.py <path/to/export.xml>` (idempotent Apple Health → `sensor_readings`).
- **NEW:** `python -m fusion.smoke_test` (full Week-1 pipeline end-to-end).

**Next:** Week 2 — re-pull TTS chain from `v0-pre-rebuild` tag; OpenWakeWord + wake-word → STT → chat → TTS roundtrip. Per `docs/superpowers/specs/2026-05-27-vertical-slice-waking-empath-design.md` §8.

---

**Prior — 2026-05-27 — REBUILD IN PROGRESS.**

v0 implementation scrapped (commits `6aae6f5` + `8dd0a33` deleted iOS, chat handler, realtime classifier, cue decider, body-bridge, sleep observer, audio chain, and adjacent v0 modules). The rebuild proceeds per `docs/REBUILD_PLAN.md`, targeting the architecture in `docs/ARCHITECTURE.md`.

**Phase 0 safety net in place:**
- Code: tag `v0-pre-rebuild` at commit `22f6ffb` (on origin)
- Data: Neon branch `pre-rebuild-snapshot` (`br-muddy-bonus-apu2y8kw`, all 22 tables intact)

**Nothing else from v0 currently runs.** Sleep cues, autonomous interject, sleep observer, chat handler, native iOS/Watch apps, Pi daemon (broken — Pi chat needs to migrate imports) — all gone until their replacement layers land per REBUILD_PLAN.md.

The historical body below this banner describes pre-scrap state and is progressively out of date. Each completed rebuild phase will update its relevant section.

**Prior — last pre-rebuild update (2026-05-24):** Architecture commitment #16 added (JEPA-family world model, LeWM recipe v1 target). L4 + L5 sections reframed accordingly. See `docs/ARCHITECTURE.md §2.16`.

The single page that answers "where are we, where are we going, what's blocking us?" Updated after substantive work lands. Open this any session when you need orientation.

---

## North star

**Koine Labs:** *Build the infrastructure of two worlds — the world awake and the world asleep — and the interface that makes them one.*

**Daybook is an always-on AI empath companion that knows you through your body.** Continuous biometric / neural sensing + a persistent character (Regis) that evolves with you over years. Especially attentive at night, where it monitors sleep and gently intervenes in dream patterns. **Naturally extends into clinical applications** where therapists leverage the continuous between-session companion + sleep + mood data to support patients with depression, PTSD-related nightmares, trauma processing, and related conditions.

**Three layers of the same product:**
- **Consumer empath** — bonded AI companion for dream-curious people on existing wearables (the validation wedge)
- **Clinical-grade extension** — therapist-licensed tool with between-session monitoring, IRT (Image Rehearsal Therapy) delivery, audit-grade interaction log
- **Eventual wearable form factor** — single-ear device with integrated BCI + audio + camera tether (the long-term defensibility moat)

**Three input channels (added 2026-05-17 late):**
- **Voice** (explicit speech via STT)
- **Continuous context** (ambient audio + ambient vision + BCI + biometrics — what's happening without the user saying anything)
- **Gestures** (silent, deliberate back-channel from user — tap, head nod, eye blink, voice grunt — for "yes / no / not now / look here / shut up" without speaking)

All three are first-class. Without gestures specifically, an always-on companion is forced to be reactive-only or annoying — the user needs a way to acknowledge / dismiss / redirect silently, especially in conversations or shared spaces.

**v1 validation wedge (locked):** ≥50% relative improvement in weekly dream recall vs 14-day pre-baseline. Single-subject (Aakash) for 60-90 days. This is **the proof point for the larger thesis**, not the destination — it demonstrates the empath substrate works, the character compounds, and the sleep specialization delivers measurably.

**Capital posture:** Bootstrapped through v1 validation. Capital raise only after working prototype + N=1 result + first clinical-advisory conversations land (~90-180 days out).

---

## What's actually live tonight

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
source inference/.venv/bin/activate

# Talk to Regis (general partner mode — sleep stuff only if you ask):
python -m chat.cli

# Log a dream this morning (text):
python -m recall.capture --text "I dreamed about an old library with my grandfather..."

# Log a dream via voice memo (interactive mic):
python -m recall.capture
```

Regis runs on your ChatGPT subscription (signed in as aakashjuly18@gmail.com → tokens at `~/.daybook/auth.json`). Embeddings run locally on your Mac (BGE-M3 cached at `~/.cache/huggingface`). Database is Neon Postgres.

### Talk to Regis from the phone (added 2026-05-19)

```bash
# In one terminal — FastAPI bridge
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
source inference/.venv/bin/activate && cd api
uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# In another — Cloudflare Tunnel (foreground)
bin/cloudflare-tunnel-run.sh
```

Then open the **Daybook** iOS app on your iPhone → tap "say something to regis" → real chat with `gpt-5.2 / codex` over `https://daybook.koinelabs.com`. Works from anywhere with internet (not just home Wi-Fi). For the tunnel to auto-start at boot: `sudo cloudflared service install`.

The `X-API-Key` gate (server-side: `apps/inference/.env.local`, iOS-side: `apps/ios/Daybook/Daybook-Local.plist`) keeps the tunnel URL from being a free backdoor. Both files are gitignored.

The **DaybookWatch** watch app runs the four-state face (Rest / Listen / Speak / Talk). Currently only Rest + long-press → Talk are real — Listen and Speak need WatchConnectivity wiring next.

---

## Three parallel tracks

The whole product is the intersection of these three. They run in parallel because they have independent dependencies.

### Track 1 — Bedside hardware lab

The physical sensing rig. Pi 4 brain, ESP32 satellites, EEG + bone-conduction. v3 substrate, currently in benchtop form.

| State | What |
|---|---|
| [HAVE] | Pi 4 (flashed, SSH'd), ESP32 (MicroPython, REPL over Pi USB), 2× ESP32-CAM, Arduino Uno, 3.5" TFT, 3D printer, lasers, 24/7 desktop PC (4080 Super), MacBook, Apple Watch S8/9 |
| [ORDERED — ~10 days] | BioAmp EXG Pill ($35, Tindie) — single-channel biopotential amplifier for EEG/EMG/ECG |
| [ORDERED — ~2-3 days] | TECKNET bone-conduction headphones (~$25-30, Amazon) |
| [ORDERED — ~2 days] | ESP32-CAM-MB programmer adapter board (FT232-based) |
| [DONE — 2026-05-17] | Pi OS Lite 64-bit flashed, SSH-by-key from Mac via `daybook` alias, repo cloned to `~/code/daybook` |
| [DONE — 2026-05-17] | ESP32 (CP210x) on `/dev/ttyUSB0`, MicroPython v1.28.0, mpremote REPL working, GPIO echo verified |
| [DONE — 2026-05-17] | **Pi daemon at `apps/pi/`** — sensor-source-pluggable (mock + esp32_serial + future cam/mic), cue-emitter-pluggable (stdout + future audio/haptic), imports AI brain (RealtimeClassifier + CueDecider), persists to Neon. Smoke-tested. |
| [QUEUED] | ESP32 firmware for sensor packet emission, EXG Pill electrode placement, bench tests (EMG forearm → ECG chest → EEG scalp), TFT bring-up, ESP32-CAM as multi-modal source |

**Interface to AI:** `apps/AI_PI_CONTRACT.md`. Pi daemon imports `apps/inference/{realtime,cue_decision,llm,embeddings}` and `apps/wisp/composer`. Lock-step versioned.

### Track 2 — Wisp interface (Regis)

The character + voice + audio routing.

| State | What |
|---|---|
| [DECIDED] | Persona = Regis (TBATE-inspired will-o-wisp). Dual-mode: Witness during sleep / Companion when awake. v1 = generative-from-day-one (LLM-composed utterances, not scripted variants — see commitment 8). |
| [DONE — 2026-05-17] | **`apps/wisp/PERSONA.md`** — character bible, dual-mode, canon-grounded snark + logo-grounded softness, vocabulary discipline. Now framed as a general partner; sleep work is one role among many. |
| [DONE — 2026-05-17] | **`apps/wisp/composer.py`** — generative composer: PERSONA + state + retrieved I-Model memories + moment kind → ChatClient → utterance. Validated. |
| [DONE — 2026-05-17] | **Chat Regis** (`apps/chat/`) — text REPL with persona + retrieval + memory + general-partner mode. **Use it tonight via `python -m chat.cli`.** |
| [DONE — 2026-05-17] | **Logo finalized:** `/Logo/Clear-Koine-Wisp.png` — warm amber glow, soft horns. The Witness-Mode aesthetic. |
| [NOT DECIDED] | TTS provider (ElevenLabs / Cartesia / OpenAI Voice / Sesame). Voice character / accent. |
| [NOT BUILT] | TTS wrapper, audio output to bone-conduction, voice-input STT for chat (currently keyboard-only), conversation listening (continuous mic + diarization for v2.5+), vision integration (ESP32-CAM → multimodal LLM) |

**Blocker:** Bone-conduction hardware arriving in 2-3 days unblocks voice output. TTS provider then needs a call.

### Track 3 — Backend infrastructure (data + intelligence)

| State | What |
|---|---|
| [DONE — 2026-05-17] | Postgres schema deployed (16 tables across migrations 0001-0004, pgvector HNSW indexes, branded ID system in `packages/shared/`) |
| [DONE — 2026-05-17] | Apple Health XML parser — imported 495K sensor readings, 543 sleep sessions, 7,568 stage classifications from 10-year HK export |
| [DONE — 2026-05-17] | **Sleep-stage classifier** — production binary REM model on 249 sessions. F1=0.45, ROC-AUC=0.72 (honest floor for HR-only passive Watch data; EEG unlocks the rest) |
| [DONE — 2026-05-17] | **`apps/inference/realtime.py`** — RealtimeClassifier with rolling buffers, per-epoch features, optional `user_state_estimate` persistence |
| [DONE — 2026-05-17] | **`apps/inference/cue_decision.py`** — CueDecider with 5 safety gates. Tested: both cues landed inside Apple-labeled REM segments. |
| [DONE — 2026-05-17] | **`apps/inference/llm/`** — Sign-in-with-ChatGPT (PKCE OAuth → Codex backend → gpt-5.2). ChatClient.auto() routes Codex (signed-in) vs Gateway (fallback stub). |
| [DONE — 2026-05-17] | **`apps/inference/embeddings/`** — BGE-M3 local (1024-dim, ~217ms/embed on Mac), pgvector retrieval, embed_and_store helper |
| [DONE — 2026-05-17] | **`apps/recall/`** — morning capture: text or voice (local Whisper) → dream_recalls + embedding → optional Regis "Held." |
| [DONE — 2026-05-17] | **`apps/chat/`** — chat handler + retrieval (last 6 turns + top-5 similar + top-3 observations + opt-in health summary) + 9 trait-drift rules + observation extractor. Made into general partner (no default health injection). |
| [DONE — 2026-05-17] | Migrations 0002 (regis_observations, regis_trait_history, user_state_estimate) + 0003 (embedding_cluster_memberships, i_model_activations, i_model_novelty_log, regis_moments, vector dim 1024) + 0004 (chat_conversations, chat_messages) |
| [DONE — 2026-05-17, evening parallel build] | **Voice output** — `apps/inference/audio/` (Kokoro local TTS, `am_michael` voice, ~310ms synth, macOS `say` fallback) + `apps/wisp/voice_chain.py` (composer → TTS → speaker). Regis speaks aloud through Mac speakers / BT headphones. Mode-aware delivery (witness slow/soft, companion normal). |
| [DONE — 2026-05-17, evening parallel build] | **Voice input** — `apps/inference/llm/stt.py` (Whisper via recall's local model) + `apps/chat/voice_cli.py` (ENTER-to-record voice REPL with audio out). `--no-speak` for text-only. |
| [DONE — 2026-05-17, evening parallel build] | **Capture flows** — `apps/intent/capture.py` (sets intent, embeds text) + `apps/mood/capture.py` (logs valence/arousal/notes, embeds notes). CLI `python -m intent.capture --text "..."` / `--voice`. |
| [DONE — 2026-05-17, evening parallel build] | **ESP32 mock firmware** — `apps/pi/firmware/sensor_mock.py` (MicroPython). Realistic synthetic HR/HRV/resp/spo2 packets matching AI_PI_CONTRACT. When EXG Pill arrives, swap mock source for real ADC reads — rest of pipeline unchanged. Cross-runs on host CPython for testing. |
| [DONE — 2026-05-17, evening parallel build] | **I-Model self-expansion** — `apps/inference/imodels/{clusterer,activator,novelty}.py`. HDBSCAN (DBSCAN fallback). Smoke: 30 seeded embeddings → 2/3 thematic clusters discovered; activator returns top match at 0.79-0.87 sim to query. Persists to i_model_clusters + embedding_cluster_memberships + i_model_activations + i_model_novelty_log. |
| [DONE — 2026-05-17, evening parallel build] | **Sleep observer** — `apps/inference/sleep_observer.py`. After each sleep session: LLM extracts 1-5 grounded regis_observations from sensor aggregates + stage timeline + dream recalls + intents. Smoke on real session produced *"Short sleep: 6.5h vs 7-day average 8.3h"* + *"Fragmented staging: 13 epochs with 12 transitions"*. |
| [DONE — 2026-05-17, evening parallel build] | **Chat consolidator** — expanded `apps/chat/consolidator.py` from stub. Daily job: pulls day's chat_messages, LLM extracts 0-5 observations, embeds + persists. Skips days with <3 messages. |
| [DONE — 2026-05-17, evening parallel build] | **Vision** — `apps/inference/llm/vision.py`. **Codex multimodal works via Aakash's ChatGPT plan** (validated). `describe_image()` returns natural-language image description in ~2-3s. |
| [DONE — 2026-05-17, evening parallel build] | **RSS news pull** — `apps/inference/news/feeder.py` (HN + Verge + Economist default feeds). `relevant_for_user()` filters via embedding similarity. CLI `python -m news.feeder --relevant`. |
| [DONE — 2026-05-17, evening parallel build] | **Walking-remark prototype** — `apps/wisp/walking_remark.py`: vision frame or news item → composer → Regis comment. Real output on logo: *"Looks like a fish that forgot what it was for."* On HN article: *"Funny how the future keeps dragging us back to a handset and a coin slot."* |
| [NOT BUILT] | "Should I speak now?" autonomous decider for waking moments, continuous-mic conversation listening + diarization, Gateway client real impl, calibration layer for classifier probabilities, web frontend for chat, privacy-by-default sensor consent framework, custom wearable form-factor experiments, regis trait-drift on sleep events |

### Track 4 — Native apps (added 2026-05-19)

iPhone + Apple Watch as the user's visible surfaces into Regis. Built on the same FastAPI brain.

| State | What |
|---|---|
| [DONE — 2026-05-19] | **`apps/api/`** — FastAPI bridge exposing chat / recall / observations / sessions / persona / compose / health. Single-user (hardcoded to Aakash's UUID). 21 routes. |
| [DONE — 2026-05-19] | **`apps/api/auth.py`** — X-API-Key middleware. Loopback bypass for Mac-local dev, but Cloudflare-proxied requests (detected via `cf-connecting-ip`) always require the key. Public paths (`/`, `/health`, `/docs`) bypass for edge health checks + browsable OpenAPI. |
| [DONE — 2026-05-19] | **Cloudflare Tunnel** at `https://daybook.koinelabs.com` → `localhost:8000`. Named tunnel `daybook` on Aakash's Cloudflare account. Setup automated by `bin/cloudflare-tunnel-setup.sh`; foreground runner `bin/cloudflare-tunnel-run.sh`; or install as launchd service. |
| [DONE — 2026-05-19] | **iOS app (`apps/ios/Daybook/`)** — three-room shell from Claude Design (Now / Self / Connections). Regis breathing center, halo + drifting ping bubbles, body whispers + micro-states, talk pill. Self has long-form portrait + body aurora + memory threads + dreams (all in honest empty states). Connections has BCI hero + wearables + apps + tuning + permissions. ChatOverlay wired to real `/chat/conversations` → real Regis replies. |
| [DONE — 2026-05-19] | **watchOS app (`apps/ios/DaybookWatch Watch App/`)** — single-face, four-state (Rest / Listen / Speak / Talk). Rest is default; long-press → Talk; Listen + Speak are server-push (not wired). HealthKit live HR query (UI shows `—` until Health capability enabled in Xcode + permission granted). Auto-launches alongside the iOS app via scheme post-action. |
| [DONE — 2026-05-19] | **Daybook app icon** — Icon Composer source bundle preserved at `apps/ios/Daybook/Daybook.icon` (Liquid Glass / layered format, for when actool support stabilizes). Current `AppIcon.appiconset` ships flat PNGs for iOS Default / Dark / Tinted appearance modes + watchOS. |
| [NOT BUILT] | WatchConnectivity push (phone → watch Listen state when Regis surfaces a ping; phone → watch Speak state when TTS active), audio recording on watch long-press → forward to phone → Mac, voice-mode chat on iOS (text-only for now), HealthKit pull on iOS to feed body whispers, SSE stream from FastAPI for proactive pings on Now, HTTPS-friendly real auth (multi-user later — current X-API-Key is single-key personal). |

---

## v3 always-on vision — where we stand

Your v3 vision (single-ear device, walks with you all day, sees what you see, hears your conversations, reads your BCI, comments on news, evolves with you over time) is the long arc. **The substrate is roughly 30-35% built** when weighted across all layers:

| Layer | % of v3 done | Notes (updated after 2026-05-17 evening build) |
|---|---:|---|
| Software brain (intelligence, persona, memory, retrieval, LLM) | ~85% | Composer + retrieval + I-Model clusterer/activator/novelty + sleep observer + consolidator all live. |
| Sensing layer (BCI, vision, mic input, multi-modal) | ~25% | Apple Watch ✓, vision ✓ (Codex multimodal works), mic input ✓ (Whisper). EEG arriving; continuous BCI emotional state classifier still v1.5 work. |
| I/O layer (voice in/out, vision in, audio routing) | ~80% | Text ✓, voice in ✓ (STT), voice out ✓ (Kokoro TTS), vision in ✓. Now also: **native iOS chat ✓, Apple Watch face ✓ (rest + talk)**. Pending: bone-conduction routing, voice-mode in iOS, WatchConnectivity push. |
| Autonomous behavior (when to speak, what to notice) | ~15% | Sleep cues fire autonomously. News pull + walking remark are the first non-sleep autonomous triggers. Still need the "should I speak now?" decider that gates ALL autonomous interjections. |
| Memory + evolution (clustering, activation, consolidation, observers) | ~75% | Clusterer ✓, activator ✓, novelty ✓, sleep observer ✓, chat consolidator ✓. Missing: trait drift on sleep events, nightly cron scheduling. |
| Hardware form factor | ~5-10% | Bedside rig in progress (Pi chat); wearable form factor is years out. |

**Weighted overall: ~50-55% toward v3** — up from ~30-35% this morning. The build session covered: voice (both directions), vision, news, I-Model evolution, mock firmware for the EEG-arriving day. The remaining 45-50% is mostly: hardware integration, the autonomous-interjection decider (the hardest research problem), and form factor.

See full gap analysis in conversation log (2026-05-17 session). Reproduced as TODO list below.

---

## Roadmap — what comes next, in leverage order

### Near-term (weeks, mostly hardware arrival-gated)

1. **Bone-conduction arrives (~3 days)** → TTS pick + audio output → Regis speaks aloud
2. **EXG Pill arrives (~10 days)** → bench tests → real EEG data → retrain classifier with EEG features → emotional state estimation (arousal/valence) instead of just sleep stage
3. **Voice STT for chat (live, not batch)** → talk to Regis instead of typing
4. **ESP32-CAM integration** → image capture → multimodal LLM call → "what is Regis looking at?"

### Mid-term (1-3 months)

5. **Continuous BCI emotional state classifier** (arousal/valence from EEG bands; populates user_state_estimate during the day, not just sleep)
6. **"Should I speak now?" decider** — the autonomous-interjection brain. Combines BCI state + recent interruption rate + novelty of pending message + user preferences. *This is the research problem of v3.*
7. **Walking-remark capability** — camera frame + simple object/scene detection + LLM comment via composer
8. **Internet pull** — RSS / news / social → Regis can reference what you're reading
9. **I-Model clusterer + activator + novelty detector** — the self-expansion machinery (commitment 6)
10. **Continuous-mic conversation listening** — mic on, speaker diarization, live transcript

### Long-term (6-18 months)

11. Nightly memory consolidation cron
12. Trait drift via RL (heuristics → learned from outcomes)
13. Persistent always-on companion daemon (transitions from session-based to continuous)
14. Wearable form-factor experiments (ear-EEG modules)
15. Privacy-by-default sensor consent framework (every reading carries consent context)
16. Multi-modal real-time fusion at composition time

### Years out (v3 hardware reality)

17. Custom single-ear form factor (integrated BCI + mic + speaker + camera tether + battery)
18. Whoop-style swappable battery (never charge the device itself)
19. Daily-wear ergonomics
20. Local LLM on-device option (no OpenAI dependency for privacy mode)

---

## Gaps preventing v1 (the bedside REM-cue + dream-recall loop)

In rough order of blocking severity:

1. **No EEG data yet.** Hardware in transit ~10 days. v1 can ship without EEG using passive Watch data (F1=0.45 — usable for low-stakes whispers) but EEG unlocks better quality.
2. **No live sensor capture path.** ESP32 firmware → Pi daemon → Postgres. Pi daemon ready; ESP32 firmware not started.
3. **No TTS pick + audio routing.** Persona is written; need a voice + synth + bone-conduction routing. Blocked on bone-conduction arrival (~3 days).
4. **No dream-recall measurement habit yet.** Aakash hasn't started the 14-day baseline journal. Without that, v1's success metric has no comparison. **Highest-leverage non-engineering thing he can do tonight.** (Or use `python -m recall.capture --text "..."` each morning to log via the system itself.)
5. **CLAUDE.md was stale** (old Lullaby narrative) — **fixed 2026-05-17**.

---

## What's true *right now*, in three sentences

- **Regis is functionally complete from the neck up.** He talks (chat or voice), listens (voice in or text), speaks aloud (Kokoro TTS), sees (Codex multimodal), reads the world (RSS), remembers (embeddings + observations + traits), evolves (clusterer + activator + novelty + consolidator), and notices things on his own (sleep observer extracts real grounded notes after sessions). Only thing missing is the BCI signal itself (EXG Pill arriving) and the audio routing to bone-conduction hardware (arriving in days).
- **The ESP32 mock firmware closes the simulation loop.** Even before EXG Pill arrives, the full pipeline can run on synthetic data: mock firmware → Pi daemon → classifier → cue decider → composer → TTS → Mac speakers. When the EXG Pill lands, only the firmware swaps from mock to real ADC reads — nothing else changes.
- **The single highest-leverage thing right now** is logging daily dreams via `python -m recall.capture --text "..."` — every log embeds, populates the substrate, makes Regis's retrieval increasingly personal. The 14-day baseline starts the moment you do.

---

## Canonical references (read these for depth)

- **`docs/RUNBOOK.md`** — every command you need to run anything: chat from Mac, phone via tunnel, full always-on daemon, dream log, smoke tests. Scenario-indexed.
- **`docs/POSITIONING.md`** — full strategic anchor (customer, problem, solution, defensibility, expansion path)
- **`apps/wisp/PERSONA.md`** — Regis character bible (dual-mode, vocabulary, utterance slots)
- **`apps/AI_PI_CONTRACT.md`** — interface contract between AI brain and Pi daemon
- **`apps/inference/classifier/runs/20260517_v2_pure_bio/`** — recommended production classifier model
- **`apps/inference/classifier/runs/20260517_033114/RESULTS.md`** — original LOSO writeup with full honest numbers
- **`MIGRATION.md`** — what was kept vs scrapped from Lullaby
- **`docs/sessions/`** — historical session logs
- **`CLAUDE.md`** — repo orientation for future Claude sessions

---

## How to keep this doc useful

Update after substantive work lands. Don't update for trivial things. A good update: `[NOT BUILT]` → `[DONE]`, a blocker moves, a milestone shifts, or strategy changes. Date the change at the top.
