# CLAUDE.md

This file orients Claude Code sessions working in this repo. Read this first, then read `docs/STATUS.md` for current state.

> **REBUILD IN PROGRESS (started 2026-05-27).** The v0 implementation has been substantially scrapped (commits `6aae6f5` + `8dd0a33`) to make room for the architecture-aligned rebuild described in `docs/ARCHITECTURE.md` and sequenced in `docs/REBUILD_PLAN.md`. Sections below — especially the repo layout and quick-start commands — describe pre-scrap structure and are progressively out of date. **For what actually runs tonight, read `docs/STATUS.md` first.** Phase 0 safety net: tag `v0-pre-rebuild` at `22f6ffb`, Neon branch `pre-rebuild-snapshot`.

## What this project is

**Daybook is an always-on AI empath companion that knows you through your body.** Continuous biometric / neural sensing (Apple Watch today, BCI via BioAmp EXG Pill in days, custom wearable later) + a persistent character (**Regis**, a will-o-wisp TBATE-inspired) that evolves with the user over years.

> **2026-05-29 — direction reframe (near-term MVP).** The immediate build target is the **waking, distributed, multimodal contextual-awareness prototype**, not the sleep/dream-recall wedge. Concretely: the **MacBook M5 Pro is the inference node** running the custom fusion pipeline; a **Raspberry Pi + ESP32 are sensor satellites** carrying the **EEG/BCI (BioAmp EXG Pill, in build), a webcam, and a mic**. Raw multimodal signals flow satellites → laptop → fusion → Regis → I-Models, assembling a live "what is happening" map Regis reasons over (north star: walking down the street, fully sensed). **Sleep/dream-recall remains the long-term validation wedge — deferred to a later prototype variation, not abandoned — and sleep stays a continuous biometric data source *during* the MVP** (capture across both Waking and Sleep meta-contexts per commitment #14, so the substrate accumulates paired day+night data). See `docs/POSITIONING.md` (2026-05-29 third amendment) and `docs/STATUS.md`.

Three concentric product layers, all sharing the same underlying architecture:

1. **Consumer empath** — the bonded AI companion. v1 wedge: dream-curious people on existing wearables.
2. **Clinical-grade extension** — therapist-licensed tool for between-session monitoring + sleep/dream intervention (PTSD nightmare disorder, depression with disordered sleep, trauma processing).
3. **Wearable form factor (v3+)** — eventual single-ear device with integrated BCI + audio + camera tether. The long-term defensibility moat.

Especially attentive at night, where it monitors sleep and gently intervenes in dream patterns. The same codebase grows from v1 (bedside rig) → v3 (wearable). Form factor shrinks separately from software.

Owner: **Aakash Agrawal** (founder, Koine Labs). Solo developer, bootstrapped, vibe-coding via AI tooling. Prefers Python and TypeScript; explicitly does NOT separate "v1 prototype" from "v3 vision" — they are one continuous build.

**Long-term validation wedge (deferred, not abandoned):** ≥50% improvement in weekly dream recall vs 14-day pre-baseline, N=1 (Aakash), 60-90 days — the *demoable, fundable* sleep proof point. Per the **2026-05-29 reframe** this is no longer the *immediate* target: the near-term MVP is the waking distributed empath (above), with the sleep specialization layered on later. Sleep biometrics are still collected throughout the MVP, so this wedge's baseline accrues in parallel.

For full strategic anchor see `docs/POSITIONING.md` (especially the 2026-05-17 second amendment and the 2026-05-29 third amendment). For current state see `docs/STATUS.md`.

---

## Repository layout

This is a pnpm + turborepo monorepo, but most of the active work is Python under `apps/`.

```
daybook/
├── CLAUDE.md                       # this file
├── README.md
├── package.json                    # workspace root
├── pnpm-workspace.yaml
├── turbo.json
├── MIGRATION.md                    # what was kept vs scrapped from prior 'Lullaby' project
│
├── docs/
│   ├── POSITIONING.md              # strategic anchor — customer, problem, solution, defensibility
│   ├── STATUS.md                   # operational big picture — read after this file
│   ├── sessions/                   # historical session logs (numbered decisions)
│   ├── learning/                   # teaching docs (databases, etc.)
│   └── historical/
│
├── Logo/
│   └── Clear-Koine-Wisp.png        # the Regis visual — warm wisp, soft horns
│
├── packages/
│   └── shared/                     # TypeScript shared types (source of truth for entity shapes)
│       └── src/{types,ids}.ts      # branded IDs + entity interfaces
│
├── apps/
│   ├── AI_PI_CONTRACT.md           # interface between AI brain and Pi daemon
│   │
│   ├── inference/                  # the AI brain (Python; venv lives here)
│   │   ├── .venv/                  # Python 3.11 venv (uv-managed)
│   │   ├── .env.local              # DATABASE_URL (gitignored, live Neon creds)
│   │   ├── pyproject.toml
│   │   ├── db.py                   # psycopg connection helper — import this, not raw psycopg
│   │   ├── parse_apple_health.py   # one-shot HK XML importer (already run for Aakash's 10yr data)
│   │   │
│   │   ├── migrations/
│   │   │   ├── 0001_initial.sql            # original 11-table schema
│   │   │   ├── 0002_regis_imodels.sql      # regis_observations + traits + user_state_estimate
│   │   │   ├── 0003_self_expanding_imodels.sql  # vector(1024) + cluster memberships + regis_moments
│   │   │   └── 0004_chat_messages.sql      # chat_conversations + chat_messages
│   │   │
│   │   ├── classifier/             # sleep-stage classifier (built + trained)
│   │   │   ├── data.py             # Neon loaders
│   │   │   ├── features.py         # per-epoch feature extraction (24 features, pure bio)
│   │   │   ├── baselines.py        # majority / HR-threshold / random baselines
│   │   │   ├── train.py            # LOSO CV training
│   │   │   ├── train_production.py # final model on all data, saves to models/
│   │   │   ├── evaluate.py         # F1 / ROC / per-session metrics
│   │   │   ├── models/             # production_binary_rem.json + sidecar
│   │   │   ├── runs/               # LOSO runs + cached features parquet
│   │   │   └── notebooks/explore.ipynb
│   │   │
│   │   ├── realtime.py             # RealtimeClassifier (rolling buffers, predict_at, writes user_state_estimate)
│   │   ├── cue_decision.py         # CueDecider (5 safety gates; for sleep cue firing)
│   │   │
│   │   ├── llm/                    # Sign-in-with-ChatGPT + Codex backend
│   │   │   ├── auth/{oauth,jwt,storage,session,sign_in}.py  # PKCE flow vs auth.openai.com
│   │   │   ├── codex_client.py     # calls chatgpt.com/backend-api/codex/responses with SSE
│   │   │   ├── chat.py             # ChatClient.auto() unified interface
│   │   │   └── smoke_test.py
│   │   │
│   │   └── embeddings/             # BGE-M3 local embeddings
│   │       ├── model.py            # lazy-loaded sentence-transformers (MPS/CUDA/CPU auto)
│   │       ├── store.py            # embed_and_store helper
│   │       ├── retrieve.py         # retrieve_similar via pgvector HNSW
│   │       └── smoke_test.py
│   │
│   ├── wisp/                       # Regis character + generative composer
│   │   ├── PERSONA.md              # character bible (dual-mode Witness/Companion)
│   │   ├── composer.py             # compose_utterance(): persona + state + retrieval → ChatClient
│   │   └── smoke_test.py
│   │
│   ├── recall/                     # morning dream-recall capture
│   │   ├── capture.py              # CLI: --text or interactive mic; writes dream_recalls + embedding
│   │   ├── whisper_client.py       # local Whisper base model
│   │   ├── recorder.py             # sounddevice mic recorder
│   │   └── smoke_test.py
│   │
│   ├── chat/                       # chat Regis (general partner, sleep is one role of many)
│   │   ├── handler.py              # handle_user_message() — full turn
│   │   ├── retrieval.py            # gather_context() — last 6 turns + similar past + observations + opt-in health
│   │   ├── health_summary.py       # heuristic health-data slice (ONLY on sleep/HR keyword queries)
│   │   ├── trait_drift.py          # 9 heuristic rules updating regis_trait_history
│   │   ├── observer.py             # extracts regis_observations from notable exchanges (≥20 words gated)
│   │   ├── consolidator.py         # nightly memory consolidation stub
│   │   ├── conversation.py         # lifecycle helpers
│   │   ├── cli.py                  # interactive REPL: python -m chat.cli
│   │   └── smoke_test.py
│   │
│   ├── pi/                         # Pi-side daemon (sensor capture, cue delivery, persistence)
│   │   └── ...                     # owned by a separate Pi chat; imports apps/inference/* and apps/wisp/composer
│   │
│   ├── api/                        # FastAPI HTTP bridge — exposes the Python brain to native clients
│   │   ├── app.py                  # FastAPI app, middleware wiring, route inclusion
│   │   ├── auth.py                 # X-API-Key middleware. Loopback bypass; CF-proxied requests always require key.
│   │   ├── deps.py                 # current_user_id() — single-user prototype, hardcoded to Aakash
│   │   ├── schemas.py              # request/response models
│   │   ├── routes/                 # chat, recall, observations, sessions, persona, compose, health
│   │   ├── smoke_test.py
│   │   └── README.md               # run instructions + tunnel runbook
│   │
│   └── ios/                        # Native iPhone + Apple Watch apps (SwiftUI)
│       ├── project.yml             # xcodegen manifest — regenerates Daybook.xcodeproj
│       ├── Daybook.xcodeproj/      # generated; don't hand-edit
│       ├── Daybook/                # iPhone target
│       │   ├── DaybookApp.swift
│       │   ├── ContentView.swift   # 3-room shell (Self ← Now → Connections)
│       │   ├── Info.plist          # DaybookAPIBaseURL + DaybookAPIKey defaults (committed)
│       │   ├── Daybook-Local.plist # gitignored override (real tunnel URL + key) — written by cloudflare-tunnel-setup.sh
│       │   ├── Daybook.icon/       # Icon Composer source bundle (layered for iOS 26+; preserved for future)
│       │   ├── Assets.xcassets/    # AppIcon.appiconset (Default/Dark/Tinted), regis.imageset
│       │   ├── DesignSystem/       # Theme.swift, GlassPanel.swift
│       │   ├── Components/         # RegisCharacter, AmbientParticles, RoomBackground, ConstellationDots, SectionHeader
│       │   ├── Screens/            # NowRoom, SelfRoom, ConnectionsRoom, ChatOverlay
│       │   ├── State/              # AppState, Tweaks
│       │   └── Networking/         # APIClient (chat() lazy-creates conversation, sends X-API-Key header)
│       └── DaybookWatch Watch App/ # watchOS target — single face, four states (Rest / Listen / Speak / Talk)
│           ├── ContentView.swift   # state machine: default Rest, long-press → Talk
│           ├── WatchStates.swift   # Rest/Listen/Speak/Talk views
│           ├── WatchRegis.swift, WatchBackground.swift, WatchTheme.swift
│           ├── HeartRateClient.swift  # HKAnchoredObjectQuery for live HR (needs HealthKit capability on real device)
│           └── DaybookWatch.entitlements
│
├── bin/
│   ├── cloudflare-tunnel-setup.sh  # one-shot: create named tunnel, route DNS, write ~/.cloudflared/config.yml + Daybook-Local.plist
│   └── cloudflare-tunnel-run.sh    # foreground tunnel runner
│
└── (other usual workspace files)
```

---

## Quick start — running the live system

> **For the full command catalog** (every scenario: chat from Mac, phone via tunnel, always-on daemon, smoke tests, troubleshooting), see **`docs/RUNBOOK.md`**. The rest of this section is the bare minimum.

All Python work runs from `apps/` with the venv activated:

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
source inference/.venv/bin/activate
```

### Talk to Regis (general partner)
```bash
python -m chat.cli              # interactive REPL
# /quit to exit, /new for fresh conversation, /help for commands
```

### Log a dream
```bash
python -m recall.capture --text "I dreamed about..."   # text input
python -m recall.capture                                # interactive mic (ENTER to start/stop)
python -m recall.capture --text "..." --no-ack          # skip Regis "Held." (saves a few seconds)
```

### Bring up the HTTP bridge for the iOS / Watch apps
```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
source inference/.venv/bin/activate
cd api && uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# In another terminal — Cloudflare Tunnel (makes Mac reachable from phone anywhere):
bin/cloudflare-tunnel-run.sh
# Or `sudo cloudflared service install` once to auto-start at boot.
```

iOS + Watch apps then hit `https://daybook.koinelabs.com` (URL + API key come from the gitignored `apps/ios/Daybook/Daybook-Local.plist`, written by `bin/cloudflare-tunnel-setup.sh`).

### Sign in to ChatGPT (already done for Aakash, persists in `~/.daybook/auth.json`)
```bash
python -m llm.auth.sign_in       # OAuth-PKCE flow → opens browser → callback on :1455
python -m llm.smoke_test         # 3-test validation of LLM path
```

### Smoke tests (after changes)
```bash
python -m llm.smoke_test
python -m embeddings.smoke_test
python -m wisp.smoke_test        # full composer end-to-end
python -m chat.smoke_test        # full chat handler end-to-end
python -m recall.smoke_test
```

---

## Conventions — read before writing code

### Python
- Python 3.11+, full type hints, `from __future__ import annotations`
- `pathlib.Path`, never `os.path`
- One-line docstrings max. **No comments unless explaining non-obvious *why*.**
- Use `from db import get_conn` after `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "inference"))` — never re-implement DB connection logic.
- `DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"` (Aakash, the only user for now).
- Always tz-aware datetimes (UTC). Never strip timezone info.

### Database
- Neon Postgres (PG 17, pgvector). DATABASE_URL in `apps/inference/.env.local` (gitignored).
- Migrations are append-only and additive when possible. Apply via psycopg in a Python smoke test, NOT via `psql` (Neon connection string has special chars that break `psql` arg parsing).
- All event entities have `i_model_id UUID NULL` per the I-Model commitment.
- All vector columns are **`vector(1024)`** for BGE-M3 (not 1536 — that was the OpenAI default we moved off of).
- Polymorphic content via `kind TEXT` + `payload JSONB` (sensor_readings, regis_moments).

### LLM access
- Use `from llm import ChatClient` then `ChatClient.auto()` — never call the Codex API directly.
- `chat(system, user) -> str` for free-form. `chat_structured(system, user, schema)` for Pydantic-validated output.
- Default model: `gpt-5.2` via Codex (free, uses Aakash's ChatGPT subscription). Override per call or via env var.
- Gateway fallback path is stubbed (raises NotImplementedError until an API key is wired).

### Embeddings
- Use `from embeddings import embed, embed_batch, embed_and_store, retrieve_similar` — never call sentence-transformers directly.
- Model is BGE-M3 (1024-dim), local on the Mac via `sentence-transformers`. Auto-picks MPS on Mac / CUDA on PC / CPU fallback.
- First call loads the model (~30-40s); subsequent calls are ~200ms each.
- HuggingFace warning about unauthenticated requests is cosmetic — inference runs 100% locally, model is cached at `~/.cache/huggingface/`.

### Regis utterances
- `from wisp.composer import compose_utterance` — assembles persona + state + retrieval, returns `ComposedUtterance`.
- Pass `moment_kind` to set mode (witness vs companion). See `WITNESS_KINDS` / `COMPANION_KINDS` in composer.
- Persona file at `apps/wisp/PERSONA.md` becomes the system prompt. Edit it, no rebuild needed.

### TypeScript types
- `packages/shared/src/types.ts` is the conceptual source of truth for entity shapes.
- `packages/shared/src/ids.ts` defines branded ID types (compile-time only, zero runtime cost).
- DB schema in `apps/inference/migrations/*.sql` is the DB source of truth. Keep both in sync when changing.

---

## Architectural commitments (locked, do not violate)

These are decisions made over the development arc that future code must honor. See `memory/project_daybook.md` in the auto-memory system for the full lineage.

1. **I-Model polymorphism.** Every event entity has `i_model_id UUID NULL`. Schema + retrieval hooks present from day 1.
2. **Content polymorphism.** `regis_moments.kind` is a pluggable discriminator; cue selection is content-agnostic.
3. **Wisp-as-interface.** Audio output (eventually bone-conduction TTS) is the primary surface. Screens are for setup/debug.
4. **Three distinct I-Models.** `user_self` (what we know about the user) + `regis_of_user` (what Regis has noticed) + `regis_self` (Regis's drifting personality dials). Schema in migrations 0002 + 0003.
5. **Regis is dual-mode, not flat-toned.** Witness Mode during sleep (reverent, sparse). Companion Mode when awake (dry, teasing — canon TBATE energy). Same character, different posture based on user consciousness state.
6. **Self-expanding I-Models.** I-Models are DISCOVERED from data, not pre-defined. The three top-level categories are containers; sub-I-Models emerge via clustering. Embeddings are many-to-many with clusters (`embedding_cluster_memberships`).
7. **Moment polymorphism.** `regis_moments` is the generalized any-context Regis action log. Sleep cue, morning prompt, walking remark, conversation tease — all live here.
8. **Generative Regis from day one (not scripted variants).** PERSONA.md is the system prompt; LLM composes utterances dynamically. Scripted variants in PERSONA.md serve as few-shot examples, not the output bank.
9. **Continuous build, not phased.** v1 prototype IS the v3 substrate. Don't defer features by phase; build them when foundational, even if the matching hardware lags.
10. **Input is classified by intent AND modality (refined 2026-05-21 v3).** Two orthogonal axes at the L1 boundary: **Intent** (Explicit vs Continuous — communication-intent) and **Modality** (Voice / Text / Gesture / Biometric / Audio / Vision / BCI — signal type). Same modality can appear under different intents (voice can be explicit speech or background mumble; gestures can be deliberate pinch or involuntary blink). Downstream layers route by whichever axis matters at that step: L2 routes by modality (which library to use), L3-L4 route by (intent, modality), L5 routes by intent. Output channels are voice (primary), future haptic, future visual indicator. See `docs/ARCHITECTURE.md §2.10` for full table + lineage.
11. **Semantic-first continuous sensing (added 2026-05-17 late).** All continuous context streams (audio, video) use semantic-first architecture: continuous low-bandwidth meaningful extraction (VAD, diarization, prosody for audio; YOLO, scene class, OCR for visual) → semantic packets stored as `sensor_readings` rows. Raw pixels and raw audio are discarded after processing. Cloud LLM calls (multimodal vision, full STT) are *triggered escalation only* — never continuous. This is the only viable architecture for always-on awareness on battery / privacy / cost grounds, and aligns with how biological attention actually works (subconscious feature extraction + occasional conscious focus).
12. **Native clients talk to FastAPI, never the brain modules directly (added 2026-05-19).** iOS, watchOS, and any future client speaks HTTP to `apps/api/` — they never import `chat`, `recall`, `wisp`, etc. The bridge is the seam. Public reachability uses Cloudflare Tunnel at `https://daybook.koinelabs.com` → `localhost:8000`. Auth is `X-API-Key` (in `apps/inference/.env.local` server-side, `apps/ios/Daybook/Daybook-Local.plist` client-side, both gitignored). Middleware bypasses auth for loopback BUT enforces it whenever Cloudflare headers (`cf-connecting-ip` etc.) are present, so cloudflared-on-Mac can't be used to launder unauthenticated requests through localhost. The setup script `bin/cloudflare-tunnel-setup.sh` is idempotent and writes both the tunnel config + the iOS-side override plist.
13. **Outcome-driven action selection (split 2026-05-22, originally added 2026-05-21).** Regis's discrete-action choices (interject vs not, witness vs companion, content kind A vs B) are learned from observed outcomes via online learning. The Thompson contextual bandit (`learned_decider.py`) is the v1 mechanism; the pattern generalizes — any time L5 picks among finite options, the choice is informed by outcome labels accumulated over time. See `docs/ARCHITECTURE.md §2.13`.
14. **The pipeline operates within a meta-context that biases every layer (added 2026-05-21).** Two mutually exclusive meta-contexts (**Waking** / **Sleep**), each with sub-contexts (alert/focused/working out/...; REM/deep/core/awake-in-bed/...). Every layer's interpretation is conditioned on the active `(meta, sub)` context: L2 prioritizes different features; L3 uses different fusion weights; L4 selects different prediction models; L5 chooses different action policies (Witness vs Companion — corollary of #5); L6 selects different output channels (no TTS during deep sleep). L1 captures uniformly; biases begin at L2. See `docs/ARCHITECTURE.md §2.14` for full table + relationship to existing commitments.
15. **Regis as a modeled controlled variable in state prediction (split from #13 on 2026-05-22).** Beyond outcome-driven action selection (#13), the system eventually models how Regis's actions *causally* shape user-state trajectories — counterfactual reasoning ("if Regis does X vs Y, predicted state at t+1 = ?"). L4's `predict(axis, horizon, action)` interface preserves this destination from day one via the optional `action` parameter. v1 uses naïve action-conditioning placeholders, evolving toward proper causal modeling via the JEPA-family world model (commitment #16) as data accumulates. See `docs/ARCHITECTURE.md §2.15`.
16. **Prediction operates in latent space — JEPA-family world model (added 2026-05-24).** L4 predictors implement the Joint Embedding Predictive Architecture pattern: an **encoder** maps inputs to a compact latent state; a **predictor** forecasts future latent state conditioned on an optional **action embedding**; **projection heads** produce axis-specific distributional outputs. v1 implementation target is the **LeWM recipe** ([le-wm.github.io](https://le-wm.github.io/)): ~15M parameters, single-GPU end-to-end training, two losses (latent prediction + **SIGReg** Gaussian regularizer), Cross-Entropy Method planning over candidate actions. Cross-layer implications: L2 encoders may co-train under JEPA objective with SIGReg; L4 predictors share an underlying world model with per-axis heads; L5 transitions from Thompson bandit (#13) to CEM planning over the world model in v2 as the action-conditioning branch becomes calibrated. v1 predictors land as per-axis regression scaffolds with the L4 interface already shaped for the world-model destination, so they compose forward rather than being thrown away. See `docs/ARCHITECTURE.md §2.16` for full cross-layer breakdown.

---

## Hardware — current and pending

**On hand (Aakash):**
- Pi 4 (flashed, SSH-able as `daybook` alias from Mac, MicroPython on ESP32 over USB)
- ESP32 (one in use, more available), 2× ESP32-CAM, Arduino Uno
- 3.5" TFT touchscreen (Pi HAT), 3D printer, lasers
- Apple Watch S8 (continuous wear)
- MacBook m5 Pro (dev) 
- 24/7 desktop PC (NVIDIA 4080 Super; heavy local compute station)
- Macbook Air
- iPhone 17 pro 
- TECKNET bone-conduction headphones
- External Wireless Mics

**Ordered:**
- BioAmp EXG Pill (~10 days) — single-channel biopotential amplifier for EEG/EMG/ECG
- ESP32-CAM-MB programmer adapter board (~2 days)

**Embedding compute today:** Mac (MPS or CPU). When the Pi is running 24/7, embedding calls will route to the desktop's 4080 (not set up yet).

---

## Where Regis runs vs where the model lives

- **Persona / behavior** = `PERSONA.md` (text). Read on every LLM call as system prompt.
- **Memory of you** = pgvector embeddings (BGE-M3, 1024-dim, local) + structured tables (`dream_recalls`, `regis_observations`, `intents`, `mood_reports`). Stored in Neon Postgres.
- **Speaking voice** = Codex backend (gpt-5.2) via Aakash's ChatGPT login. No fine-tuned model. The LLM doesn't "know" anything about Daybook — it's directed entirely by system prompt + retrieved context per call.
- **Empathic substrate** = `user_state_estimate` table. Realtime classifier writes a row every 30s during a sleep session. v1.5+ will also write from chat/walking context.

---

## Things NOT to do

- **Don't preach about credentials in chat.** Aakash explicitly opted out — flag once briefly, then continue. (See auto-memory `feedback_credentials_in_chat.md`.)
- **Don't trust documentation claims about migrated/inherited code.** Always verify by running. (See `feedback_dont_assume_migrated_code_works.md`.)
- **Don't run `next build` while `next dev` is running** in the same dir — chunk conflicts. (See `feedback_nextjs_dev_vs_build.md`.)
- **Don't apply additive migrations without checking if existing tables are empty** — vector column ALTERs require dropping/recreating HNSW indexes.
- **Don't store embeddings from different models in the same column.** Vector space is model-specific; mixing is meaningless.
- **Don't inject health/sleep data into Regis's chat context by default.** Chat is general-partner mode — health data only on explicit keyword (`apps/chat/health_summary.py` is keyword-gated).
- **Don't simulate ratification on architecture decisions** without writing them to `STATUS.md` / `PERSONA.md` / `CLAUDE.md` / memory. The doc system IS the spec.

---

## When making code changes

1. Run the relevant smoke test before declaring done (`python -m {module}.smoke_test`).
2. If schema changed: write a new numbered migration, apply via psycopg from a smoke test, update the TS types in `packages/shared/`, update `STATUS.md`.
3. If persona changed: re-run `python -m wisp.smoke_test` and `python -m chat.smoke_test` to see if Regis's voice drifted.
4. If a new architectural commitment is being made: add it to the numbered list above + `memory/project_daybook.md`.
5. Always update `docs/STATUS.md` after substantive work lands. Date the change at the top.
