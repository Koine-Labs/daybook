# Waking Decision Arc — Design Spec

**Date:** 2026-05-29
**Branch context:** `feat/fill-l6-composer` (L6 already fills end-to-end)
**Goal:** Turn the assembled waking arc from *structurally mute* into one where Regis can actually choose to speak — by replacing `DefaultPolicy`'s hardcoded `passed=False` warrant gate with a real, conservative, deterministic waking "should I speak now?" policy, and adding a production runner that wires `assemble_pipeline` + `register_speaker` + the live mic producer.

**Status:** design only. No code written yet. This file is source of truth for the implementing agents.

---

## 0. The problem, stated precisely

Today the production default L5 policy (`decision/policies/default.py`) has a single warrant gate that is a literal placeholder:

```python
def gate_clearly_warranted(ctx: DecisionContext) -> GateResult:
    return GateResult("clearly-warranted", passed=False, detail=_PLACEHOLDER)
```

`all_passed` is therefore always `False`, so `DefaultPolicy.decide` always returns `action="hold"`. A stimulus driven through `assemble_pipeline(bus)` (no injection) in WAKING **can never reach `interject`**. The only reason `output/test_speak_arc.py` proves "Regis speaks end-to-end" is that it INJECTS `_InterjectPolicy` via the `decision_policy=` seam. The production default arc is mute.

This spec replaces that placeholder with a deterministic warrant policy and adds a production runner so the real assembled arc can speak on the Mac.

---

## 1. The exact current flow (verified against source)

### 1.1 What L5 actually receives

`assemble_pipeline` (`core/pipeline.py`) wires L2→L6 on one bus; L1 (`sensors.participant.emit`) is the producer entry. The chain for one stimulus:

```
L1 emit  → TOPIC_SIGNAL  (SignalPacket, envelope.meta_context set at emit, e.g. WAKING)
L2 register → TOPIC_FEATURE (FeatureSnapshot; audio_social → features/audio_social.py)
L3 FusionParticipant → TOPIC_BELIEF (BeliefState: one AxisEstimate per registered axis)
L4 prediction.participant → TOPIC_PREDICTION (ONE Prediction PER FRESH AXIS)
L5 decision.participant → TOPIC_ACTION (ActionDecision)
L6 output.participant → TOPIC_OUTPUT (OutputDirective) → speaker sink speaks voice
```

**Key fact #1 — L5 sees a `Prediction`, not a `BeliefState`.** `DecisionContext` (`decision/policy.py`) carries `prediction: Prediction`, `meta_context: MetaContext`, `consent_scope`, `now`, `i_model_id`. The `_context_from` lift in `decision/participant.py` pulls these straight off the inbound envelope. The policy never sees the full belief — only the one axis's Prediction that triggered this `_handler` call.

**Key fact #2 — one Prediction per fresh axis.** `prediction/participant.handle_belief` iterates `fresh_axes` (sorted) and publishes a separate Prediction envelope for each. So in a single waking cycle L5's handler may be invoked multiple times (once for `meta_context`, once for `audio_social_context`, etc.). Each invocation is an independent decision. A test or runner that registers only the `meta_context` axis combiner will only ever drive the `meta_context` Prediction to L5; to exercise the social-transition warrant the fusion registry MUST produce a fresh `audio_social_context` estimate.

**Key fact #3 — the live social signal is carried, not computed, at L5.** The `audio_social_context` axis (`fusion/axes/audio_social_context.py`) fuses to `AxisEstimate.value == {"category": "alone" | "with_other"}`. The waking predictor for this axis is `StubPredictor` (registry: `("audio_social_context", WILDCARD) → StubPredictor`). `StubPredictor._flat_distribution` carries the estimate forward verbatim:

```python
Prediction.distribution == {
    "kind": "persistence",
    "informative": False,
    "carried_value": {"category": "with_other"},   # ← the live social belief
    "note": "placeholder: current state assumed to persist; ...",
}
Prediction.axis == "audio_social_context"
Prediction.confidence == None        # StubPredictor never fabricates confidence
Prediction.provenance == "placeholder"
```

So the warrant policy reads the live social category at:
`ctx.prediction.distribution["carried_value"]["category"]` **when** `ctx.prediction.axis == "audio_social_context"`.

**Key fact #4 — Predictions are SNAPSHOTS, not deltas.** A single Prediction tells the policy the *current* category, not whether it *changed*. Detecting a transition (`alone ↔ with_other`) therefore requires the policy to remember the **last category it saw per user** as its own internal state. This is the only mutable state the policy holds, and it's the same place a future bandit hangs its context. (See §2.3.)

**Key fact #5 — the envelope meta_context is the coarse enum; sub-state rides elsewhere.** `forward_envelope` inherits `envelope.meta_context` (the `MetaContext` enum: WAKING/SLEEP/UNKNOWN) unchanged L1→L6. The fine sub-tag (`"waking/focused"`, `"deep"`, `"rem"`) lives inside axis-estimate `value` dicts and, for L6 channel refinement, in `decision.gate_trace["sub_state"]`. `DecisionContext.meta_context` is therefore the coarse enum. The warrant policy keys its meta-context gate on `ctx.meta_context == MetaContext.WAKING`.

### 1.2 How `gate_trace` is built today (the style to mirror)

`decision/policy.py` provides the auditable machinery:
- `GateResult(name, passed, detail)` with `.to_dict()`.
- `run_gates(gates, ctx)` — evaluates ALL gates (no short-circuit) so the trace records every verdict.
- `gate_trace_dict(results, *, policy)` → `{"policy", "all_passed": all-passed?, "gates": [...]}`.

`sleep_cue.py` is the reference pattern: five named pure-predicate gates, `run_gates` → `gate_trace_dict`, `cleared = trace["all_passed"]`, `action = "interject" if cleared else "hold"`, honest rationale either way. **Mirror this exactly.** `DefaultPolicy` already follows the shape — only the gate bodies are placeholders.

### 1.3 What `decide` does with the result (unchanged)

`decision/participant.decide` lifts `DecisionContext`, calls `select_policy(ctx)` (→ `default` for WAKING/UNKNOWN, `sleep_cue` for SLEEP via `intent_dispatch`), calls `policy.decide(ctx)`, and `forward_envelope`s the `ActionDecision` onto `TOPIC_ACTION`. L6 (`output/participant.py`) emits NOTHING on `action == "hold"`; on `interject` it selects a channel (`channels.select_channel(WAKING) → "voice"`), renders text, publishes an `OutputDirective`. The speaker sink (`output/speaker.py`) speaks voice directives with non-empty text.

**The protocol (ActionDecision/Prediction/BeliefState shapes, the 6 topics, Transport ABC, `core/protocol/*`) MUST NOT change.** Everything below fits inside the existing `DecisionContext → ActionDecision` contract.

---

## 2. The deterministic waking warrant policy

### 2.1 Where it lives

Replace the body of `decision/policies/default.py` (same file, same `DefaultPolicy` class name, same `name = "default"`, same registry wiring in `decision/registry.py` and `intent_dispatch.py` — no routing changes). The class keeps the `Policy` protocol shape: `name: str`, `decide(ctx) -> ActionDecision`.

**One structural change:** `DefaultPolicy` becomes **stateful** (it remembers the last social category per user — Key fact #4). The module-level `DEFAULT_GATES` list-of-pure-functions pattern from `sleep_cue` is replaced by **methods** on the instance (or closures bound at `decide` time) so the gates can read instance state. The registry already instantiates `DefaultPolicy()` once (`_REGISTRY = {... DefaultPolicy.name: DefaultPolicy(), ...}`), so a single long-lived instance naturally accumulates last-seen state across decisions in a run. Keep the gates as named predicates returning `GateResult` and still run them through `gate_trace_dict` for an honest trace.

### 2.2 The three gates (ALL must pass → interject; else HOLD)

HOLD remains the safe default. Any uncertainty → hold. Gates evaluated with NO short-circuit (so the trace records every verdict), mirroring `run_gates`.

**Gate A — `meta-context` (companion posture, #5/#14).**
- PASS iff `ctx.meta_context == MetaContext.WAKING`.
- FAIL for SLEEP (shouldn't reach here — `sleep_cue` owns SLEEP) or UNKNOWN (don't risk waking-voice when context is uncertain — fail-safe, mirrors `channels._unknown_choice`).
- detail records the observed meta_context.

**Gate B — `salient-fresh-signal` (something worth remarking on).**
This is the heart of the warrant. PASS iff the inbound Prediction represents a **salient, fresh** signal. Concretely, v1 keys on a **social-context transition** (the live belief now flowing — Key fact #3):
- The Prediction must be for `axis == "audio_social_context"`. (A Prediction for any other axis → this gate FAILS with detail "axis not warrant-bearing"; that decision HOLDs. This is intentional: `meta_context`/other axes don't by themselves warrant speech in v1.)
- Extract `category = ctx.prediction.distribution.get("carried_value", {}).get("category")`. If missing/None → FAIL ("no social category in prediction").
- Compare to the policy's remembered `last_category[user_id]`:
  - First observation for this user (no prior) → **FAIL** ("first observation, no transition to remark on; establishing baseline"). Record the category as the new baseline (see §2.4 on when state is committed).
  - `category == last_category` → **FAIL** ("no transition: still {category}").
  - `category != last_category` → **PASS** ("transition {old}→{new}"). This is the salient event: the user just became alone, or someone just joined.
- Freshness: the Prediction rides a fresh axis (L3/L4 already gate freshness — stale axes never produce a Prediction, per `BeliefState.get` + `prediction.participant` `fresh_axes`). The gate additionally records `prediction.made_at` vs `ctx.now` in its detail for auditability, and FAILs if the carried estimate is older than a conservative bound (reuse `FRESH_SECONDS = 300` from the axis as the ceiling) — defensive, since a fresh Prediction should already satisfy this.

> v1 scope (YAGNI): the ONLY warrant-bearing salient signal is the `audio_social_context` transition. The gate is written so additional fresh high-confidence axis changes can be added as further PASS branches later without changing the policy's shape. Do not add them now.

**Gate C — `rate-limit` (Regis isn't chatty).**
- PASS iff no interjection has fired for this user within the last `MIN_INTERVAL_SECONDS` AND the per-window cap isn't exceeded.
- v1 concretely: a single `MIN_INTERVAL_SECONDS` cooldown (suggest **300s**, matching the social axis freshness horizon — conservative, tune later) tracked as `last_interjection_at[user_id]`. Optionally a `MAX_PER_WINDOW` cap (e.g. ≤ N interjections per rolling hour) — keep it to the cooldown for v1 unless trivial; YAGNI.
- First-ever decision for a user → cooldown not yet armed → this gate PASSES (it's the salience gate that holds the first observation, not the rate-limit gate).
- detail records seconds-since-last-interjection (or "no prior interjection").

**Decision:** `cleared = all gates passed`. `action = "interject" if cleared else "hold"`. `mode = "companion"` always (waking posture, #5). `content_kind`: on interject, set to a waking moment kind — use **`"conversation_tease"`** (a `COMPANION_KINDS` value; matches the existing speak-arc fixture and `ComposerRenderer`'s default `moment_kind`). On hold, `content_kind = None`.

**rationale string (must explain WHY):**
- interject: e.g. `"social context shifted alone→with_other; waking + cooldown clear — remarking"`.
- hold: the first FAILING gate's reason, e.g. `"holding: no transition (still alone)"` / `"holding: cooldown active (120s < 300s since last)"` / `"holding: meta_context unknown"`.

### 2.3 State the policy holds (minimal, deterministic)

```python
self._last_category: dict[str, str]       # user_id → last social category seen
self._last_interjection_at: dict[str, datetime]   # user_id → tz-aware UTC of last interject
```

Both keyed by `user_id` (single-user today, but keep it keyed — cheap, correct). All datetimes tz-aware UTC. No DB, no global mutable module state beyond the single registry-held instance. Deterministic: identical inputs + identical prior state ⇒ identical decision.

### 2.4 State-update ordering (must be deterministic and testable)

- **`_last_category[user]`** is updated to the current category **whenever a social-context Prediction is observed** — i.e. on every `decide` call that carries `axis == "audio_social_context"` with a readable category, regardless of whether the decision interjects or holds. This makes "transition" mean "differs from the previous social observation," which is the honest semantics. Update it AFTER computing the gate verdict (so the gate compares against the prior value), then store the new value for next time.
- **`_last_interjection_at[user]`** is updated to `ctx.now` **only when the decision actually interjects** (all gates cleared). A held decision must not arm the cooldown.
- Predictions for non-social axes do not touch either state field (Gate B fails fast on them).

### 2.5 gate_trace shape (auditable, mirrors sleep_cue)

`gate_trace_dict([...], policy="default")` →
```json
{
  "policy": "default",
  "all_passed": false,
  "gates": [
    {"name": "meta-context", "passed": true,  "detail": "waking"},
    {"name": "salient-fresh-signal", "passed": false, "detail": "no transition: still alone"},
    {"name": "rate-limit", "passed": true,  "detail": "no prior interjection"}
  ]
}
```
On interject, add a top-level `"sub_state"` key IF a finer waking sub-tag is available (so L6 channel refinement can read it) — optional, only if the Prediction carries one; not required for v1 (waking already maps to voice without sub-state). Keep YAGNI: do not invent sub_state.

### 2.6 The #13 bandit seam (scaffold, DO NOT build the bandit)

This deterministic warrant is the **pre-bandit scaffold** for commitment #13 (outcome-driven action selection / Thompson bandit in `learned_decider.py`). Keep the seam clean:
- The warrant verdict (the three gates) is the single decision point a learned decider later replaces. Structure `DefaultPolicy.decide` so the "should I interject?" boolean is computed in one isolated place (e.g. the gates produce `cleared`), and document with a one-line comment that this boolean is the swap point for `learned_decider`.
- Each decision is already **loggable as an outcome-labelable event**: the `ActionDecision` carries `gate_trace` (the feature snapshot of WHY), `decided_at`, `user_id`, `i_model_id`, `action`, `content_kind`. That is exactly the (context, action) pair #13 needs; a nightly job later labels the outcome. **Do not add persistence here** — just ensure the gate_trace is rich enough to reconstruct the decision context (it is: meta-context, category transition, cooldown state all appear in gate details).
- Add a module docstring note: *"Deterministic pre-bandit scaffold for commitment #13. The `cleared` warrant boolean is the seam a Thompson contextual bandit (`learned_decider.py`) replaces; every decision's `gate_trace` is the outcome-labelable context. The bandit is NOT built here."*

---

## 3. The runner module (production wiring, OFF the CI path)

### 3.1 Where + what

New file: `apps/inference/runtime/waking_arc.py` (new `runtime/` package with `__init__.py`). A small production-wiring module — NOT a test, NOT imported by any CI-path module.

It assembles and starts the full live waking arc on the Mac:
1. `bus = MessageBus()` (in-process transport).
2. `assemble_pipeline(bus)` — **no injection kwargs**, so the production default runs: real `FusionParticipant` (live `audio_social_context` fusion from bus packets), real `DefaultPolicy` (the new warrant policy), default `ComposerRenderer` (real Regis voice, lazy LLM).
3. `register_speaker(bus)` — **no `speak=` kwarg**, so the real `_default_speak` (lazy `audio.streaming.speak_streaming`) is used. (TTS only fires on a warranted interject in waking — voice channel.)
4. Attach the **live mic producer**: call `voice.loop.listen_continuous(bus=bus, user_id=...)`. That path constructs `AudioBusSink(bus)` and a `ContinuousProcessor`, runs the always-on mic loop, and emits privacy-gated `audio_social_context` / `audio_prosody` / `audio_ambient` `SignalPacket`s onto `TOPIC_SIGNAL` via `sensors.participant.emit`. Those flow L2→L6 through the assembled arc; a social transition that clears the warrant makes Regis speak.

Provide a `main()` / `if __name__ == "__main__":` entry: build bus, assemble, register speaker, then block in `listen_continuous(bus=bus)`. Keep a `--user-id` / `DAYBOOK_USER_ID` default of `DEFAULT_USER_ID`.

**Meta-context note:** `listen_continuous` → `AudioBusSink` → `sensors.participant.emit` defaults `meta_context=MetaContext.UNKNOWN`. For the waking runner, the producer's emitted signals should ride `MetaContext.WAKING` so Gate A passes and L6 selects voice. The mic adapter (`AudioBusSink`) currently calls `emit(...)` without a meta_context arg. **Smallest honest fix:** have the runner pass a `meta_context=MetaContext.WAKING` hint through to the sink, OR (preferred, smaller surface) the runner sets up the producer so its emissions carry WAKING. Implementer's call between: (a) threading a `meta_context` kwarg through `AudioBusSink.__init__` → `emit`, default UNKNOWN (additive, no behavior change for existing callers/tests), or (b) a thin runner-local wrapper sink. Prefer (a) — it's additive, keeps `emit`'s existing default, and is the natural home for the meta-context the runner knows. Do NOT change `emit`'s signature semantics or any payload shape. Whatever is chosen must not break `sensors`/`fusion` tests (verify with the CI command).

### 3.2 Why it's off the CI path

- It needs a real microphone (`sounddevice` InputStream), the `[voice]` extra (torch/audio/whisper), and a real TTS device — none present in CI (which installs only the lean base, no `--extra voice`, and has no audio hardware).
- CI runs `python -m pytest core sensors features fusion prediction decision output -q`. `runtime/` is **not** in that path, so the runner is never collected. Keep it import-clean: all heavy imports (sounddevice, audio, voice.continuous internals) stay LAZY/inside functions exactly as `voice.loop` already does, so even importing `runtime.waking_arc` doesn't pull audio into the graph. The module-level imports are limited to `MessageBus`, `assemble_pipeline`, `register_speaker`, enums, and `voice.loop` (whose module-level imports are themselves light — it lazies sounddevice/audio inside `listen_continuous`). Verify `python -c "import runtime.waking_arc"` succeeds with no DATABASE_URL and no audio stack.

### 3.3 What the runner does NOT do

- No DB writes (the bus-mode `AudioBusSink` path is pure-bus; persistence is a later sink).
- No new protocol, no new topics.
- No test of the runner on CI. A single optional `runtime/` smoke (manual, hardware-gated) MAY be added but must be excluded from the CI pytest path (it's not in the CI module list, so simply living under `runtime/` already excludes it). Prefer: no runner test; the warrant policy + arc test (below) carry the proof.

---

## 4. Test plan (hardware-free, network-free, DB-free, ON the CI path)

All tests run under the CI command from `apps/inference` with NO `DATABASE_URL`:
```
python -m pytest core sensors features fusion prediction decision output -q
```
Baseline today: **160 passed.** New tests live in `decision/` and `output/` (both on the CI path). The runner's `runtime/` is NOT in the path → never collected by CI.

### 4.1 Unit tests for `DefaultPolicy` (in `decision/test_default_policy.py`, new file)

Drive `DefaultPolicy.decide` directly with hand-built `DecisionContext`s (the cheapest, most deterministic level — mirrors how `test_participant.py` builds `_ctx`). Helper builds a `Prediction` with a chosen `axis` and `distribution={"kind":"persistence","carried_value":{"category": <cat>}, ...}`.

Cases (one fresh `DefaultPolicy()` instance per test for isolation; for sequence tests, one instance across calls):
1. **first social observation HOLDs** — single `with_other` Prediction, no prior. Asserts `action=="hold"`, salience gate failed with "first observation" reason, `_last_category` now recorded.
2. **no transition HOLDs** — feed `alone` twice; second decision holds ("no transition: still alone").
3. **transition INTERJECTS** — feed `alone` then `with_other` (cooldown clear). Second decision: `action=="interject"`, `mode=="companion"`, `content_kind=="conversation_tease"`, all three gates passed, rationale mentions transition.
4. **wrong meta-context HOLDs** — a real transition but `meta_context=UNKNOWN` (and a separate case `SLEEP`): meta-context gate fails → hold. (SLEEP won't route here in prod, but the gate must still fail-safe if asked.)
5. **rate-limit HOLDs** — transition that would interject, but `_last_interjection_at` set to `ctx.now - 60s` with `MIN_INTERVAL_SECONDS=300` → rate-limit gate fails → hold ("cooldown active"). Then advance `now` past the cooldown and feed another transition → interjects.
6. **non-social-axis Prediction HOLDs** — `axis=="meta_context"` Prediction → salience gate fails ("axis not warrant-bearing"), holds, and does NOT mutate `_last_category`.
7. **cooldown armed only on interject** — assert a held decision does not set `_last_interjection_at`; an interject does.
8. **gate_trace is honest + JSON-serializable** — every decision's `gate_trace` has `policy=="default"`, three named gates `{meta-context, salient-fresh-signal, rate-limit}`, `all_passed` consistent with `action`, and `ActionDecision.to_dict()` round-trips (isoformat `decided_at`).
9. **determinism** — identical ctx + identical prior state → identical `ActionDecision` (compare `to_dict()` minus timestamps).

### 4.2 Update existing `decision/test_participant.py`

`test_waking_routes_to_default_policy_and_holds` currently asserts the WAKING default HOLDs. With the new policy a single WAKING `_inbound` (its `_prediction` axis is `sleep_stage`, distribution `{"rem":..,"core":..}`) still HOLDs — because Gate B fails on a non-social axis. **So this test stays green as-is** (the default still holds for that input). Verify, don't rewrite. If the assertion message references "placeholder phase," soften it, but the behavioral assertion (`action=="hold"`, policy `"default"`, companion) holds. Add ONE new test there proving a WAKING social-transition `_inbound` (two calls through `decide` with `audio_social_context` predictions) reaches `interject` — closing the unit-level loop at the participant boundary.

### 4.3 The headline integration test — DEFAULT policy reaches interject+speak (in `output/test_speak_arc.py` or a sibling `output/test_default_warrant_arc.py`)

This is the proof the task demands: the **DEFAULT assembled arc (no `decision_policy=` injection)** reaches interject+speak on a warranted synthetic stimulus. Model it on the existing `test_speak_arc.py` but DROP the `_InterjectPolicy` injection.

Setup (all in-memory, no network/DB/audio):
- `monkeypatch` `wisp.composer.compose_utterance` to a deterministic stub (reuse the existing `_patch_composer` helper) so `ComposerRenderer` (the production default) renders without the LLM.
- `bus = MessageBus()`.
- `assemble_pipeline(bus, fusion_registry=<social-axis fixture>)` — **NO `decision_policy=`**, so the real `DefaultPolicy` runs. The fusion registry must produce a **fresh `audio_social_context` AxisEstimate** (so L4 emits a `audio_social_context` Prediction that reaches L5). Provide a combiner returning `AxisEstimate(axis="audio_social_context", value={"category": <cat>}, timestamp=now, confidence=0.8, source="...test_fixture", fresh_for_seconds=300)`. (The default `StubPredictor` in the real registry turns this into the carried-value Prediction L5 reads — no predictor injection needed.)
- `register_speaker(bus, speak=spoken.append)` — recorder, no audio path.
- Subscribe a recorder to `TOPIC_OUTPUT`.

Driving the warrant (transition requires TWO observations — Key fact #4):
- **Stimulus 1:** emit a waking signal with the fixture combiner returning `category="alone"`. `l1.emit(bus, reading, meta_context=MetaContext.WAKING)`. Expect: `outputs == []`, `spoken == []` (first observation HOLDs — baseline established).
- **Stimulus 2:** flip the fixture combiner to return `category="with_other"` (e.g. a mutable holder the combiner closes over, or two registries on two `assemble_pipeline`s sharing one `DefaultPolicy` instance — simplest is a mutable `{"cat": "alone"}` the combiner reads). emit again with `meta_context=MetaContext.WAKING`. Expect:
  - exactly ONE `OutputDirective` on `TOPIC_OUTPUT` with the entry `trace_id`, `channel=="voice"`, `mode=="companion"`.
  - `directive.text == COMPOSED_TEXT` (the mocked composer ran via the real `ComposerRenderer`).
  - `spoken == [COMPOSED_TEXT]` (sink spoke it).
  - the L5 `ActionDecision` on `TOPIC_ACTION` has `action=="interject"`, `gate_trace["policy"]=="default"`, all three gates passed.

> Caveat to handle: the fusion fixture registry should register ONLY `audio_social_context` (not `meta_context`) so L4 emits exactly one Prediction per stimulus and the social-axis decision is the only one reaching L5 — keeping the "exactly one OutputDirective" assertion clean. (Real prod registers both axes; the meta_context Prediction would simply HOLD via Gate B, emitting nothing — but registering only the social axis avoids over-asserting on ordering.)

### 4.4 HOLD cases through the DEFAULT assembled arc (same test file)

Prove the assembled DEFAULT arc stays silent when not warranted:
- **No transition** — two `alone` stimuli: `outputs == []`, `spoken == []`, composer never called (`calls == []`).
- **Wrong meta-context** — a real `alone→with_other` flip but `l1.emit(..., meta_context=MetaContext.UNKNOWN)`: Gate A fails → hold → no directive, no speak. (Also confirms L6/channels would withhold on UNKNOWN regardless.)
- **Rate-limited** — drive a transition that interjects, then immediately drive another transition (within cooldown) and assert the second produces no new OutputDirective (cooldown gate holds). This requires controlling `now`; since `DecisionContext.now = datetime.now(timezone.utc)` is set in `_context_from`, the assembled-arc rate-limit case is awkward to control deterministically at the integration level. **Recommendation:** prove rate-limit at the UNIT level (§4.1 case 5, where `ctx.now` is hand-set) and keep the integration HOLD cases to "no transition" + "wrong meta-context" (both fully deterministic without clock control). YAGNI: don't add a clock-injection seam to the participant just for one integration assertion.

### 4.5 Existing tests stay green

- `output/test_speak_arc.py`'s two existing tests (which inject `_InterjectPolicy` / `_HoldPolicy`) are untouched and MUST remain green — the injection seam still works.
- `core/test_pipeline.py`'s `run_silent_hold_arc` (uses the real default policy on a non-warranted stimulus) stays green — the default still HOLDs on its input (non-social or single-observation). Verify; if it asserts a "placeholder" rationale substring, update only that string assertion, not the behavior.
- Full suite must end at **≥160 passed** (160 existing + new tests), 0 failures.

---

## 5. Implementation checklist (for the agents)

1. Rewrite `decision/policies/default.py`: stateful `DefaultPolicy` with three named gates (meta-context, salient-fresh-signal, rate-limit), per-user `_last_category` + `_last_interjection_at`, deterministic state-update ordering (§2.4), honest `gate_trace` via `gate_trace_dict`, `mode="companion"`, `content_kind="conversation_tease"` on interject. Module docstring documents the #13 bandit seam. Constants: `MIN_INTERVAL_SECONDS = 300`, reuse social `FRESH_SECONDS` ceiling. No DB, no network, no LLM.
2. Do NOT touch `decision/registry.py`, `decision/intent_dispatch.py`, `decision/participant.py`, `decision/policy.py`, `core/pipeline.py`'s `assemble_pipeline` signature, or any `core/protocol/*`. The new policy slots into the existing `DefaultPolicy` registry entry unchanged.
3. Add `decision/test_default_policy.py` (§4.1). Extend `decision/test_participant.py` with the one new interject test (§4.2).
4. Add the DEFAULT-arc integration test(s) (§4.3, §4.4) under `output/` (new file `output/test_default_warrant_arc.py` to keep `test_speak_arc.py` focused, OR append — implementer's call; new file is cleaner).
5. Create `runtime/__init__.py` + `runtime/waking_arc.py` (§3) — production wiring, lazy heavy imports, NOT on the CI path. If choosing the additive `meta_context` kwarg on `AudioBusSink`/`emit` (§3.1), make it additive with default UNKNOWN and re-run the `sensors`/`fusion` suites.
6. Run the CI-mirror command from `apps/inference` with NO DATABASE_URL; confirm ≥160 passed, 0 failed. Confirm `python -c "import runtime.waking_arc"` imports clean (no audio/DB).
7. Agents author + self-test. **Do NOT git commit** (controller commits).
8. After landing: per the theory-aligner workflow, this fills the L5 waking warrant — note it advances commitment #13's scaffold and honors #5/#14 (companion posture, voice channel) and #3 (voice primary). Update `docs/STATUS.md` (controller step, not the authoring agents).

---

## 6. Out of scope (YAGNI — explicitly NOT building)

- The Thompson bandit / `learned_decider.py` itself (only the clean seam).
- Decision persistence / nightly outcome labeling.
- Additional warrant-bearing axes beyond `audio_social_context` (the gate is shaped to extend, but v1 ships one).
- Sub-state-aware waking channels (waking → voice is enough; no `sub_state` invention).
- A clock-injection seam in the L5 participant (rate-limit proven at unit level).
- Any change to the frozen protocol, the 6 topics, the Transport ABC, or existing injection seams.
