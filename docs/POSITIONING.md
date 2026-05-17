# Daybook — v1 Positioning

**Version:** v0.1 — strategic anchor, supersedes the lucid-dream-induction framing in `Project_Lullaby_PRD_v1.1.docx`
**Drafted:** 2026-05-16
**Owner:** Aakash Agrawal
**Status:** Strategic anchor before v1 build. Operationalized by a forthcoming PRD v2.0.

This document is the strategic anchor for the v1 product. It exists so that when we are deep in implementation and the next pivot temptation arrives, we can come back here and remember what we decided to build, for whom, against what, and how we will know it worked. Edits to this document are intentional, dated, and visible.

---

## 1. What Koine Labs is

Koine Labs builds the infrastructure of two worlds — the world awake and the world asleep — and the interface that makes them one.

Time is the fundamental principle of reality, and the one most efficiently trapped. Our vocation is to extend accessible time itself, and the work done within it. The third of human life currently spent in unconscious dormancy is what we mean to return.

Daybook is the first product. It is one specific product within Koine Labs' broader vision, not the whole vision.

## 2. What Daybook is

Daybook is a **24/7 multi-modal personal cognitive companion**. It sits on top of the wearable you already own (Whoop, Oura, Apple Watch), integrates with your existing cognitive tools (Anki, journal, calendar), and optionally adds neural-grade sensing (EEG) for users who want it. Daybook closes the loop between what you do during the day and what your brain consolidates during the night, with measurable next-day output as the outcome.

The product is not a wearable. The product is the **intelligence and intervention layer** above the wearables.

## 3. The v1 wedge — sharp, narrow, defensible

### Customer

**Anki-using Whoop / Oura / Apple Watch wearers.** Specifically:

- Already wears a 24/7 biometric tracker (or accepts wearing one)
- Already uses spaced-repetition for serious learning (Anki, Mochi, RemNote)
- Accepts subscriptions for cognitive tools
- Cares about measurable retention, not vague "better sleep"
- Reachable through high-density learning communities (r/Anki, r/medicalschool, r/lawschool, r/languagelearning, language-learning Discord servers)

This is a behavior-defined segment with measurable baselines. Not lucid-dream hobbyists. Not generic "knowledge workers." Not biohackers shopping for sleep gadgets. **Specifically:** people who study daily and have a number — their Anki retention rate — they want to move.

### Problem

The brain consolidates a fraction of what you encountered during the day during slow-wave sleep. Targeted memory reactivation (TMR) cueing — playing audio related to studied content during slow-wave sleep — has been shown in peer-reviewed research (Paller, Stickgold, Konkoly) to measurably increase next-day recall. **No consumer product currently delivers TMR.** Anki users feel the gap viscerally — they know they're losing material between study session and next review.

### Solution at v1

Daybook v1 plays subtle audio cues of your Anki review content during your slow-wave sleep, on hardware you already own, and measures your next-day Anki retention improvement on its own dashboard.

### Success criterion

Across N=5–10 users running Daybook for 30 nights each, **average Anki retention improves measurably vs. each user's pre-Daybook baseline**. Target: ≥15% relative improvement in retention rate. Validated on the user's own Anki performance, not on Daybook's internal scoring.

## 4. Architecture — the integration layer

```
   WEARABLE (user owns)             WAKING-DAY INPUTS              DAYBOOK INTELLIGENCE             NEXT-DAY OUTPUT
   ───────────────                  ─────────────────              ──────────────────────            ──────────────
   Whoop, Oura, Apple Watch  ───┐                                                                  ┌──▶  Anki retention rate
                                ├─▶  HR / HRV / temp / SpO2  ───┐                                  ├──▶  Recall test
   iPhone (existing Lullaby      │                              │                                  │
   app: sonar, audio,            ├─▶  Breathing / motion / ─────┤                                  │
   accelerometer aggregation)    │   audio features              │                                 │
                                 │                              ├─▶  Sleep stage classifier  ──┐  │
   EEG (EXG Pill, optional)  ───┘                              │   (per-user, calibrated)     │  │
                                                                │                              │   │
   Anki (export, or API)     ──────────▶  Today's review cards  ├─▶  TMR cue selector  ────────┤   │
   Calendar (optional)       ──────────▶  Day context           │   (which audio, when)        │   │
   Journal (optional)        ──────────▶  Intent / topics       │                              │   │
                                                                │                              ▼   ▼
                                                                │                      During-sleep
                                                                │                      audio cue delivery
                                                                │                      (bone conduction, pillow
                                                                │                       speaker, or AirPods)
                                                                │                              │
                                                                │                              ▼
                                                                └────────────  Personal model updates ◀───┘
                                                                              (this user's specific
                                                                               cue thresholds, retention
                                                                               sensitivity, sleep patterns)
```

**Key architectural commitments:**

- **No new wearable for v1.** Users keep whatever they have. Daybook reads from HealthKit (Apple Watch), Whoop API, Oura API. If they have nothing, they can use the existing iPhone-based Lullaby sleep tracking.
- **EEG is optional enhancement, not required.** EXG Pill (in shipment) is for Aakash's N=1 validation and for users who want neural-grade precision. The product works without it.
- **The personal model is the moat.** Every architectural decision serves this: per-user calibration, longitudinal data accumulation, multi-modal fusion. Hardware is fungible; the model trained on your specific data is not.
- **Privacy by default.** Raw audio and EEG never leave the device (per existing Lullaby v1 commitment). Only feature vectors and outcomes go to the cloud.

## 5. Competitive landscape — and why each gap matters

| Territory | Who's there | What they do | What they don't do |
|---|---|---|---|
| Pre-sleep neuro-intervention | Somnee | 15-min tACS to nudge sleep architecture | No during-sleep intervention. No content awareness. No waking-day integration. No multi-modal. |
| Passive sleep tracking | Apple Watch, Whoop, Oura | Continuous biometrics, sleep scoring | Score in, score out. No intervention. No content. No personal-model integration. |
| Sleep environment control | Eight Sleep | Mattress temperature regulation | Physical only. No cognitive layer. |
| Sleep-state EEG meditation tools | Muse | EEG + meditation/sleep app | Single-device ecosystem. No third-party wearable integration. No waking-day loop. No cognitive content. |
| Open EEG hardware | OpenBCI | DIY kit for researchers | Not a product. No app. No integration. |
| Lucid dream induction | LucidCatcher, REM-Dreamer | LED flashes during REM | Single intervention modality. Niche. No platform. |
| **During-sleep content-aware cueing for memory consolidation** | **No one** | — | Open territory |
| **Waking-day data → sleep intervention loop** | **No one** | — | Open territory |
| **Multi-modal personal cognitive model on top of existing wearables** | **No one** | — | Open territory |

The last three are Daybook's territory. They are not a feature; they are a category.

**The clean differentiation that survives any competitive challenge:**

> *Every existing product gives you data about yourself. Daybook gives you measurably better tomorrow.*

Measurable tomorrow — Anki retention, recall rate, next-day focus — is something no incumbent measures, no incumbent positions on, and no incumbent has architected their product to deliver. They are all locked into the score model because that is what hardware-first companies sell. Daybook is software-first.

## 6. Honest defensibility analysis

We do not have unique patented technology. The moat is **execution speed × data depth × ecosystem-agnostic integration.**

### Real risks

**Risk 1: Whoop could ship this.**
They have the data, the customer base, the engineering team. Mitigation: they would need (a) audio cue delivery hardware (they lack it), (b) EEG-validated sleep staging precision (their wrist sensors cannot do content-aware cueing precision), (c) third-party cognitive integrations like Anki (outside their competence). By the time a $1B+ company ships this, a focused startup has 12–18 months of cumulative personal-model data its users cannot easily replicate elsewhere. Not bulletproof. Real.

**Risk 2: Muse could add the cognitive layer.**
Muse has EEG, an app, sleep tracking. Mitigation: Muse is committed to its single-device ecosystem. The "multi-wearable integration" architecture is structurally hostile to their business model. They cannot credibly say "use what you have" without cannibalizing their hardware sales.

**Risk 3: The moat is data-effect, not unique IP.**
The defensibility is execution speed plus retention-driven personal-model depth. That is real but not patented technology. Mitigation: ship the v1, get users into the data flywheel, accumulate longitudinal data. The longer Daybook has been collecting a user's integrated cognitive data, the harder it is for any competitor to credibly say "switch to us" without that history.

**Risk 4: TMR effect sizes in the literature are modest.**
The published research shows TMR works, but the effect sizes (typically 5–15% improvement on specific recall tasks) are real but not dramatic. Mitigation: we will report what we measure honestly, and the target is 15% relative improvement (in the upper range of published effects). If effect sizes turn out smaller in real-world conditions, that informs whether to continue or pivot. The constitution commits us to publishing failures, not just successes.

**Risk 5: The audio cue delivery in real consumer conditions may be harder than the research suggests.**
Research conditions use professional headphones, controlled sleep environments, precise cue timing. Consumer environments have bedmates, noise, varying cue precision. Mitigation: this is exactly what the N=1 study is for. We do not assume the research translates; we test it.

### What needs to be true for the v1 thesis to hold

1. TMR cueing during slow-wave sleep delivers measurable retention improvement in real consumer conditions (not just clinical studies)
2. Consumer-grade sensors (Apple Watch + iPhone + optional EEG) can detect slow-wave sleep with enough precision to time cues correctly
3. Anki users will tolerate beta-grade hardware and software setup for a measurable improvement in their study practice
4. The personal model improves with use enough to produce a switching cost that retains users

If 1 or 2 is false, the product does not work. If 3 is false, we cannot find early adopters. If 4 is false, the moat is shallow.

The v1 experiment specifically tests 1 and 2 simultaneously, using Aakash as the N=1.

## 7. What we are explicitly NOT building at v1

To keep v1 sharp, the following are deferred:

- **Lucid dream induction** as the lead use case. Option preserved for v2; not pursued at v1. We will not build features that specifically target lucid dreaming.
- **Pre-sleep neurostimulation** (Somnee's territory). Deferred to v2+. Audio cues are not stimulation; we are not competing on Somnee's mechanism.
- **Sleep quality improvement as the primary outcome.** Sleep quality is a secondary metric. The primary outcome is cognitive output (Anki retention).
- **Building a new wearable.** Use what the user owns. Custom hardware is a v3+ question.
- **Subscription-locked features at v1.** Free for the prototype users. Subscription model is a later decision.
- **Mass-consumer onboarding.** v1 is for technical, motivated early adopters who tolerate jankiness.
- **Clinical or medical positioning.** Wellness/cognitive-performance positioning only. No FDA path, no medical claims. (May change at v3+.)
- **Apple ecosystem exclusivity.** v1 launches on iOS because the existing Lullaby app is iOS, but Android/Web roadmap is open for v2.

## 8. The platform expansion path (v2 and beyond)

v1 ships one specific feature: TMR for memory consolidation, measured by Anki retention.

Once that ships and works, the platform expands:

- **v1.5: Positive dream reinforcement.** The same architectural loop with different content + measurement modules. Waking-day analysis identifies what's "working" (positive states, biometric peaks, emotionally significant moments). During REM, audio cues reinforce that material. Measurement shifts from Anki retention to mood (PANAS), HRV recovery patterns, dream-content sentiment. Customer expands beyond Anki users to anyone who wants their sleep to integrate emotional content as well as cognitive content.
- **v1.6:** Generalize cue content beyond Anki — Roam/Tana note review, journaling content, calendar context, intentions
- **v2:** Add lucid dreaming as an optional cue mode (the territory we deliberately reserved)
- **v2.5:** Sleep quality intervention via audio + light timing (Somnee's territory, but our story is "we don't need to stimulate your brain, we play the right thing at the right time")
- **v3:** Pre-sleep intervention layer (audio-based, ritual integration)
- **v4+:** Custom hardware (when the platform proves out and capital is available)

Every expansion is a marginal feature on top of an already-proven platform. v1 proves the loop works. Every later version adds to the existing loop.

### Critical architectural commitment from v1.5 being on the roadmap

Memory consolidation (v1) and positive dream reinforcement (v1.5) are *the same loop with different content and measurement modules*. v1 must therefore be built with **polymorphism in the cue-content layer, the sleep-stage targeting, and the measurement layer** from day one:

- **Cue selection algorithm** is content-agnostic; content adapters are pluggable (Anki adapter for v1; emotional-moment adapter for v1.5)
- **Sleep-stage targeting** is a parameter of the cue plan, not hardcoded (SWS for v1; REM for v1.5)
- **Measurement layer** is pluggable; the dashboard surfaces whichever measures are active for the user's enabled modes
- **Personal model schema** is extensible along the content axis (content-effectiveness for v1; emotional-effectiveness for v1.5)

The marginal cost of building polymorphism in at v1 is small. The cost of retrofitting later is enormous. This is the second "build it shaped right from day one" architectural commitment, alongside the I-Model architectural commitment.

### Third architectural commitment: wisp-as-interface

Daybook's user-facing presence is not a dashboard or an app — it is a **personal auditory companion (the wisp)** that lives in bone-conduction headphones, learns from the user's day, and transitions seamlessly into sleep. The wisp's working character name is **Regis** (homage to *The Beginning After the End*; subject to public-name review before launch). The wisp is the literal embodiment of the koinelabs.com mission line — the *interface that makes the two worlds one*.

The wisp evolves in capability over versions:
- **v1 (minimal wisp):** a single consistent TTS voice, ~10 scripted moments per day (pre-sleep plan, post-wake check-in, evening intent, etc.), no live conversation. Establishes the *character gestalt*.
- **v2:** simple conversational moments (call-and-response, contextual short exchanges).
- **v3:** full real-time voice AI with personality consistency, streaming, sub-second latency.
- **v4+:** visual presence (AR / on-screen wisp), then environmental awareness (camera), then eventually neural integration.

v1 architecture must support this evolution without rebuild:

- **TTS layer is abstracted** — one provider chosen for v1 (ElevenLabs / Cartesia / OpenAI Voice) but the voice-identity-to-audio pipeline can swap providers without changing the persona
- **Persona spec exists as data, not code** — a config + prompt template that all wisp utterances draw from; v1 uses it for scripted moments, v2+ uses it for live generation
- **Wisp event stream is the underlying data model** — every wisp utterance is a row with timestamp, context, content, audio reference; v1 has ~10/day, v3 has continuous
- **Bone-conduction audio routing is the primary output channel** from day one, even when v1 only plays scripted utterances
- **I-Model awareness hook exists** — the wisp queries which I-Model is active before speaking; v1 may not act on it strongly, v2+ does

This is the third "shape right from day one" architectural commitment, alongside I-Model polymorphism (#1) and content polymorphism (#2).

### Naming clarification

- **Company:** Koine Labs (parent vehicle)
- **Product:** Daybook (the system — the daily practice + the wisp + the loop)
- **Character within product:** Regis (the wisp — working name, public-name review before launch)
- **Web app domain:** app.koinelabs.com (subdomain of koinelabs.com, no separate brand domain at v1)

### Repository structure (decided 2026-05-17)

Two repos under the `Koine-Labs` GitHub org. Not polyrepo per-component.

- **`Koine-Labs/website`** — the marketing / manifesto site (Next.js). Deploys to koinelabs.com. Already exists.
- **`Koine-Labs/daybook`** — **monorepo** containing every component of the Daybook product:

  ```
  daybook/
  ├── apps/
  │   ├── web/            Next.js — deploys to app.koinelabs.com
  │   ├── ios/            Swift Xcode project (iOS + watchOS)
  │   └── inference/      Python FastAPI — deploys to Railway / Vercel Functions
  ├── packages/
  │   ├── shared/         TypeScript types, JSON schemas, API contracts (source of truth)
  │   ├── persona/        Wisp persona spec (prompts, voice config, scripted moments)
  │   └── ui/             Shared React components for web + future surfaces
  ├── firmware/           Arduino C++ for ESP32 + BioAmp EXG Pill
  ├── tooling/            CI scripts, deployment configs, codegen
  └── docs/               Architecture spec, PRD, internal docs
  ```

  Tooling: Turborepo + pnpm workspaces (TS), `uv` or `poetry` for the Python workspace, Xcode for iOS, arduino-cli/platformio for firmware.

**Why monorepo for the product, polyrepo at the org level:**

- **Shared types are load-bearing.** Web, iOS, and Python all need to agree on what a `SleepSession` / `CueEvent` / `WispUtterance` is. Polyrepo means defining these in three places that drift; monorepo means one source of truth with generated bindings per language.
- **AI tools (Cursor, Claude Code) work dramatically better with the whole product codebase visible** — atomic refactors across web + iOS + Python become one commit instead of four coordinated PRs across four repos.
- **The marketing site has fundamentally different concerns** (audience, lifecycle, content rhythm) and stays separate to keep both clean.

## 9. Brand line — for external use

> *Daybook. Your sleep, working for you.*

Or:

> *You already wear a Whoop or Apple Watch. You already use Anki. Daybook is the cognitive companion that makes the sleep you already get into measurable cognitive gains tomorrow.*

(The shorter line is for hero copy. The longer line is for an investor or first-customer 30-second pitch.)

## 10. Relationship to existing Lullaby PRD

The Feb 2026 Lullaby PRD v1.1 framed the product as lucid-dream induction via REM detection + haptic cueing. That framing is **superseded** by this positioning document.

The existing engineering work — iOS app, watchOS app, Cloudflare data server, Python analysis pipeline, inference server — is **not superseded**. The technical foundation is correct: continuous sensor collection, multi-source data integration, server-side ML pipeline, personal-model calibration loop. What changes is:

- The lead use case shifts from lucid-dream induction to TMR/memory consolidation
- The cue modality shifts from haptic (Watch) to audio (bone conduction / pillow speaker / AirPods)
- The waking-day data layer (Anki integration, journaling, calendar) becomes a primary input rather than a v3+ future consideration
- The customer shifts from lucid-dream practitioners to Anki users on existing wearables
- The success metric shifts from "lucid dream rate" to "next-day Anki retention"

A forthcoming PRD v2.0 will operationalize these changes against the existing codebase.

---

## Decision log

| Decision | Rationale | Date |
|---|---|---|
| v1 customer = Anki users on existing wearables | Behavior-defined segment with measurable baseline; sharpest competitive gap | 2026-05-16 |
| v1 success metric = Anki retention improvement | Falsifiable; user can verify on their own Anki | 2026-05-16 |
| Daybook positioning replaces Lullaby lucid-dream positioning | Lucid dreaming market too narrow; TMR scientifically defensible and serves broader audience | 2026-05-16 |
| Multi-wearable integration over building new hardware | Hardware is fungible; the personal model is the moat | 2026-05-16 |
| EEG (EXG Pill) is optional enhancement, not required | Keeps v1 reachable without prerequisite hardware purchase; EEG validates the consumer-sensor pipeline | 2026-05-16 |
| Lucid dreaming preserved as v2 option, not pursued at v1 | Reserve the territory without committing v1 attention | 2026-05-16 |

## Open questions for the v2.0 PRD

1. How exactly does Anki integration work — file export, API, plugin, or some combination?
2. What audio cue format works best — single-word association, phrase, brief tone? What does the research recommend, and what can a user record at scale?
3. What is the minimum number of cue nights vs. control nights for a meaningful N=1 result?
4. How do we handle users whose existing wearable charging breaks the 24/7 continuity? (Whoop is 24/7; Apple Watch is not.)
5. What does the morning recall test look like — a delta to the user's Anki review session that morning, or a separate test?
6. How do we serve users who do not use Anki but use a different spaced-repetition system?
