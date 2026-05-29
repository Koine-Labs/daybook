# L3 affect axes — design

**Date:** 2026-05-29
**Status:** approved (synth reconciled against three adversarial critiques; two BLOCKING fixes applied)
**Piece:** add L3 fusion axes that consume affect-relevant features **already flowing on the bus**. Two axes ship; one defers. This is a thin, contract-early build (#9) that drains real and currently-wasted signal into the per-axis belief log and the JEPA flywheel (#16).

## Context

L3 fusion has five live axes (`meta_context`, `sleep_stage`, `audio_social_context`, `cognitive_load`, `visual_context`). The synth proposed three affect axes; three adversarial critiques verified every claim against the code. The reconciled scope is **two axes shipped, one deferred**:

- **`arousal_inferred` — SUBSTANTIVE.** A real biometric `FeatureSnapshot` flows on `TOPIC_FEATURE` today (`features/biometric.py::extract` produces the 24 REM feature_cols under `payload["features"]`, `payload["kind"]=="biometric_window"`). HR/HRV are a genuine physiological arousal signal. Keystone of this piece.
- **`affect_prosody` — SCAFFOLD (honestly an arousal proxy, NOT valence).** A real prosody `FeatureSnapshot` (`payload["kind"]=="audio_prosody"`, prosody dict under `payload["prosody"]`) rides the bus and **dies at L3 with zero subscribers** — the only audio axis fires on `audio_social_context`. Landing this drains a wasted stream. Prosody energy/pitch_std are *activation* (arousal), not valence: `prosody.py::_classify_tone` puts `warm` and `raised` both at high energy, so joy and rage are indistinguishable. We ship an honestly-labeled prosodic-arousal proxy and defer true (sign-discriminating) valence.
- **`state_declared` — DEFER.** No explicit-intent path reaches the bus. `Intent.EXPLICIT` exists only as an enum value + a `Literal` default; no live producer constructs it. The one real transcript (`voice/loop.py::run_turn`) bypasses the bus entirely (STT → `compose_utterance` → TTS). An L3 `state_declared` axis registered today would return `None` → OFFLINE on every packet. Building it honestly is a multi-layer L1→L2→L3 project (new EXPLICIT producer + new L2 LLM affect classifier + short-fresh L3 axis), out of scope for "add axes consuming flowing features." Deferred to a dedicated piece.

**Ground truth verified on disk:**
- The axis contract: `fuse_from_feature(packet, *, now=None) -> AxisEstimate | None`. `packet` is an untyped `FeatureSnapshot`; the discriminator is `packet.payload["kind"]`, read defensively `getattr(packet, "payload", {}) or {}`. There is **no `fusion/contract.py`** — `AxisEstimate`/`BeliefState` live in `fusion/belief_state.py`. `fuse_from_feature` never sees the `MessageEnvelope`; `trace_id`/`meta_context`/`consent_scope`/`i_model_id` ride the envelope and are inherited by `forward_envelope`.
- **`AxisEstimate` constructor** (`belief_state.py`): `axis, value, timestamp, confidence, source, meta_context=None, i_model_id=None, fresh_for_seconds=DEFAULT_FRESH_SECONDS (120)`. `timestamp` must be tz-aware UTC (`__post_init__` raises otherwise). `method` and `scaffold` are NOT constructor fields — they live **inside `value`**.
- **`hr_pct_above_baseline` is near-constant on the live path** (verified `classifier/features.py:116,160` + `features/biometric.py:163-166`): `hr_pct_above_baseline = (hr_w > hr_session_median).mean()`, and `hr_session_median` is the median over the *same* bundle's HR readings the epoch window draws from. On the single-window nowcast path it is within-window dispersion (~constant, no arousal-level information), NOT elevation vs a personal resting baseline. **→ drives BLOCKING fix #1.**
- **No personal baseline exists anywhere on the bus.** No stored resting HR/HRV, no diurnal/long-horizon reference, no z-scoring. The longest reference is 300s in-window context + up to 5 prior-epoch `hr_mean`s. So a population-style heuristic with documented placeholder constants is the only honest v1.
- **The biometric snapshot's `meta_context_hint` is `None`** (`biometric.py::extract` never sets it). The same biometric snapshot flows under BOTH meta-contexts (`WatchBusSink` stamps the *envelope* `meta_context`, default `UNKNOWN`/`SLEEP` on replay). The REM SLEEP-gate at `prediction/feature_participant.py` works only because it is a **bus participant** reading `inbound.meta_context` off the envelope — an L3 `fuse_from_feature` axis cannot do this. **→ drives the #14 honesty posture below.**
- **Prosody dict shape** (`prosody.py::ProsodyFeatures.to_dict`): `energy, pitch_mean_hz, pitch_std_hz, speaking_rate_wpm, tone`; passed through verbatim as `payload["prosody"]` by `features/audio_social.py:38`. `audio_adapter.py:24` defines `KIND_PROSODY = "audio_prosody"`.
- **Migration 0009 reserves names in a free-TEXT column comment with NO CHECK constraint** (`migrations/0009...sql:21`): the comment lists `arousal_inferred`, `state_declared`; prosody is reserved only under the legacy backward-compat name `valence_inferred` (line 64-76, "kept for backward-compat even though…"). `affect_prosody` is NOT in the comment — safe to use (no DB constraint blocks it; L3 does not persist to `user_state_estimate` today). **No new migration needed.**
- **Consent inherits, no new scope.** `arousal_inferred` consumes biometric (`apple_health_v1` via `hk`), `affect_prosody` consumes audio (`mic_continuous_v1` via `voice`); `consent_scope` rides the envelope unchanged via `forward_envelope`. The axis never sets/checks consent.
- **Registry-set test** is `test_default_registry_references_five_live_axes` at `test_participant.py:114-116`, asserting exactly the 5-axis set.

## Design

Two new live-only axes mirroring `cognitive_load.py` verbatim (pure, DB-free, no `fuse_recent`, no `db` import, no `sys.path` insert). Both: defensive `kind` reject → `None`; second `None` for present-but-unusable signal; `method`+`scaffold:True` inside `value`; honest constant `confidence`; module consts `AXIS`/`SOURCE`(ending `.v1_heuristic`)/`FRESH_SECONDS`; timestamp `= getattr(packet,"timestamp",None) or now or datetime.now(timezone.utc)`; `i_model_id` left default `None` (inherit gap #1).

### New: `apps/inference/fusion/axes/arousal_inferred.py`

Module constants:
```python
AXIS = "arousal_inferred"
SOURCE = "L3.fusion.arousal_inferred.v1_heuristic"
FRESH_SECONDS = 120  # physiology shifts fast; matches cognitive_load/meta_context, < sleep_stage's 600s
KIND = "biometric_window"

# v1 calibration placeholders — NOT fitted to Aakash's physiology. Flagged for the
# EXG-Pill / real-watch calibration step, exactly like cognitive_load's _ENGAGE_LO/_HI.
HR_LO, HR_HI = 55.0, 110.0     # bpm: resting-ish floor -> exertion ceiling
HRV_LO, HRV_HI = 20.0, 70.0    # ms (RMSSD-style): low HRV -> high sympathetic arousal
```

Signature + computation:
```python
def fuse_from_feature(packet, *, now: datetime | None = None) -> AxisEstimate | None
```
1. `feats = getattr(packet, "payload", {}) or {}`; if `feats.get("kind") != KIND: return None`.
2. `f = feats.get("features", {}) or {}`. Read `hr_mean`, `hrv_mean`, `hr_slope`, `hr_pct_above_baseline` via a NaN-safe helper (`None` if missing or `math.isnan`).
3. If **both** `hr_mean` and `hrv_mean` are unusable → `return None` (no signal → OFFLINE).
4. **BLOCKING FIX #1 — arousal scalar uses ONLY physiologically-meaningful within-window features:**
   - `hr_component = clamp((hr_mean - HR_LO)/(HR_HI - HR_LO))` when `hr_mean` present.
   - `hrv_component = clamp((HRV_HI - hrv_mean)/(HRV_HI - HRV_LO))` (inverse) when `hrv_mean` present.
   - `arousal = 0.6*hr_component + 0.4*hrv_component`, renormalizing the weights over whichever components are present (if only one is available, it carries full weight). Clamp `[0,1]`.
   - **`hr_pct_above_baseline` is NOT weighted into the scalar** — verified ~constant within-window dispersion on the live single-window path, so weighting it injects a constant bias and wastes weight on noise. It is exposed in `value` (with `baseline="in_window_only"`) for documentation/future-use only, never moving the number.
5. `band()` via the standard cuts: `low < 0.34`, `medium < 0.67`, else `high`.
6. `hr_trend` = `"rising"`/`"falling"`/`"flat"` from `hr_slope` sign (None → omit/`"flat"`); optional note, not in the scalar.

`value` shape:
```python
{
  "arousal": round(scalar, 3),
  "band": "low|medium|high",
  "hr_mean": float|None,
  "hrv_mean": float|None,
  "hr_pct_above_baseline": float|None,   # exposed, NOT weighted
  "hr_trend": "rising|falling|flat",
  "method": "biometric_arousal_linear_v1",
  "scaffold": True,
  "baseline": "in_window_only",
  "meta_context_aware": False,
}
```
`AxisEstimate(..., confidence=0.4, source=SOURCE, meta_context=None, fresh_for_seconds=FRESH_SECONDS)`.

**`confidence=0.4`** — flat constant, same honesty tier as `cognitive_load` (unfitted heuristic, real signal). No count-based taper in v1 (a taper would fabricate a quality model the axis has not earned; deferred to the calibration step alongside HR_LO/HI fitting).

**`meta_context=None` (mandatory, do NOT copy `"waking"` from cognitive_load).** The honest tag: the axis genuinely cannot tell SLEEP from WAKING because the biometric snapshot's `meta_context_hint` is `None` and the envelope never reaches `fuse_from_feature`. Unlike `cognitive_load`/`visual_context` (by-construction waking-only EEG/cam streams that legitimately tag `"waking"`), biometrics flow under both frames. The raw `hr_mean`/`hrv_mean`/`hr_pct_above_baseline` are exposed precisely so the downstream layer that DOES hold the envelope `meta_context` (L4/L5, the way `prediction/feature_participant.py` reads `inbound.meta_context` for the REM SLEEP-gate) can reinterpret "high HR" as waking exertion vs sleep micro-arousal — without re-reading the biometrics. The "no arousal inference during deep sleep" suppression also defers to L5/L6 channel selection, identical to `cognitive_load`/`visual_context`. **Docstring must document this deferral exactly as cognitive_load documents its deferred `fuse_recent`.**

### New: `apps/inference/fusion/axes/affect_prosody.py`

Module constants:
```python
AXIS = "affect_prosody"
SOURCE = "L3.fusion.affect_prosody.v1_heuristic"
FRESH_SECONDS = 120  # prosody shifts fast like cognitive_load; chosen over the audio family's 300s
KIND = "audio_prosody"
```

Signature + computation:
```python
def fuse_from_feature(packet, *, now: datetime | None = None) -> AxisEstimate | None
```
1. `feats = getattr(packet, "payload", {}) or {}`; if `feats.get("kind") != KIND: return None`.
2. `p = feats.get("prosody", {}) or {}`. If `p` empty or `energy` missing → `return None` (→ OFFLINE).
3. `proxy_arousal = clamp(0.6*energy + 0.4*min(pitch_std_hz/60.0, 1.0))` into `[0,1]`. `band()` via the standard cuts. Carry `tone` through unchanged.
4. **No sign-discrimination** — `warm`/`raised` both map to high activation (forced by `_classify_tone`); the value is honestly an arousal proxy, never a valence number.

`value` shape:
```python
{
  "proxy_arousal": round(scalar, 3),
  "band": "low|medium|high",
  "tone": str,
  "energy": float,
  "pitch_std_hz": float,
  "proxy": "prosodic_arousal",
  "valence_discriminating": False,
  "method": "prosody_arousal_map_v1",
  "scaffold": True,
}
```
`AxisEstimate(..., confidence=0.3, source=SOURCE, meta_context="waking", fresh_for_seconds=FRESH_SECONDS)`.

**`confidence=0.3`** — LOWER than `cognitive_load`'s 0.4 and `visual_context`'s 0.5: prosody is a weaker, sign-unstable proxy not even measuring the axis its name might suggest. Honest floor.

**`meta_context="waking"`** — matches `cognitive_load`/`visual_context`. Prosody is a waking phenomenon in practice; this is a by-construction tag, NOT a firing gate (deferred to L5/L6). (Contrast with `arousal_inferred`'s mandatory `None` — do not let copy-paste flip either axis's tag.)

**Naming decision:** ship as `affect_prosody`, NOT `valence`. Migration 0009 deprecates `valence_inferred` ("kept for backward-compat even though…") and the signal is arousal, not valence — naming it `valence` resurrects a deprecated name AND claims a signal the code cannot back. **Docstring must DEFER true (sign-discriminating) valence** until one of: a facial-affect extractor lands in the vision lane (`SCENE_KEYS` has no face/expression field today), a waking-biometric L3 HRV path exists (HRV is currently SLEEP-locked to the L4 REM predictor), or prosody gets a trained valence model — documented exactly as `cognitive_load`/`visual_context` document their deferred `fuse_recent` paths.

### Edit: `apps/inference/fusion/participant.py`

1. Extend the `.axes` import (line 28) to add `arousal_inferred` and `affect_prosody`.
2. Add two live-only combiners following `_cognitive_load_combiner` verbatim (try → `<module>.fuse_from_feature(packet, now=now)`; except → `_offline_estimate("<axis>", now=now, reason=f"axis error: {exc!r}")`): `_arousal_inferred_combiner`, `_affect_prosody_combiner`. **No DB fallback** (no sensor table for biometric-window-as-axis or audio_prosody — same as cognitive_load/visual_context).
3. Add two `AXIS_REGISTRY` entries: `"arousal_inferred": _arousal_inferred_combiner`, `"affect_prosody": _affect_prosody_combiner`. Registry key MUST equal each module's `AXIS` constant (used as both registry key and OFFLINE-sentinel axis name).

### Edit: `apps/inference/migrations/0009_per_axis_state_and_prediction_log.sql` (comment-only, forward-consistency)

Add `'affect_prosody'` to the line-21 axis-vocabulary comment so the documented axis list stays in sync (no schema/CHECK change — column is free TEXT; this is documentation only).

### NOT changed

- **No new migration, no new consent scope, no `packages/shared` TS change.** Belief-state axis values are not DB entity shapes; consent inherits via `forward_envelope`.
- **`i_model_id` inherits gap #1.** Both axes leave `AxisEstimate.i_model_id` at default `None`, like every existing axis. Do NOT introduce a one-off; it fills systemically when clustering lands. Envelope-level `i_model_id` still propagates via `forward_envelope`.

## Test plan (CI-safe, DB-free)

Pure unit tests mirroring `fusion/axes/test_cognitive_load.py`: `from features.snapshot import FeatureSnapshot`, `from fusion.axes import <ax>`, `from fusion.belief_state import AxisEstimate`, with a `_feature(features, *, kind=...)` helper. Tests must import clean without the `[voice]` torch/audio stack (lean CI deps).

**`fusion/axes/test_arousal_inferred.py`** — helper builds `FeatureSnapshot(modality="biometric", payload={"kind": "biometric_window", "features": {...}})`:
1. High HR (e.g. `hr_mean=100`) + low HRV (e.g. `hrv_mean=25`) → `band in {"medium","high"}`, `arousal in [0,1]`, `scaffold is True`, `method=="biometric_arousal_linear_v1"`, `confidence==0.4`, `est.axis=="arousal_inferred"`.
2. Low HR (`hr_mean=58`) + high HRV (`hrv_mean=65`) → `band=="low"` and `arousal` strictly lower than case (1).
3. Clamp: huge `hr_mean` (e.g. 200) → `arousal==1.0`; tiny (e.g. 30) with high HRV → `arousal==0.0`.
4. Wrong kind (`kind="mac_activity"`) → `None`.
5. Both `hr_mean` and `hrv_mean` missing → `None`.
6. **Honest no-frame tag:** `est.meta_context is None`; value carries `hr_mean`/`hrv_mean`, `baseline=="in_window_only"`, `meta_context_aware is False`.
7. **BLOCKING FIX #1 guard:** holding `hr_mean`+`hrv_mean` fixed, two snapshots differing only in `hr_pct_above_baseline` (e.g. 0.1 vs 0.9) produce the **same `arousal` scalar** — proving `hr_pct_above_baseline` does not move the number (but is present in `value`).
8. **FRESH guard (BLOCKING FIX #2):** `est.fresh_for_seconds == 120` and `est.source.endswith("v1_heuristic")`.

**`fusion/axes/test_affect_prosody.py`** — helper builds `FeatureSnapshot(modality="audio", payload={"kind": "audio_prosody", "prosody": {...}})`:
1. High energy (0.8) + high pitch_std (50) → `band=="high"`, `proxy_arousal in [0,1]`, `proxy=="prosodic_arousal"`, `valence_discriminating is False`, `scaffold is True`, `confidence==0.3`, `meta_context=="waking"`, `est.axis=="affect_prosody"`, `est.fresh_for_seconds==120`.
2. Quiet (energy 0.05, pitch_std 5) → `band=="low"`.
3. Wrong kind (`kind="audio_social_context"`) → `None`.
4. Empty/missing prosody dict (and missing `energy`) → `None`.
5. `tone` label passes through unchanged (e.g. `tone="warm"` → `value["tone"]=="warm"`).

**`fusion/test_participant.py`** edits:
- Update `test_default_registry_references_five_live_axes` (rename to `..._seven_live_axes`) — change the asserted set from 5 to 7: `{"meta_context","sleep_stage","audio_social_context","cognitive_load","visual_context","arousal_inferred","affect_prosody"}`.
- Add a biometric-packet end-to-end test mirroring `test_live_audio_packet_fuses_social_belief_no_db`: publish a `FeatureSnapshot(modality="biometric", payload={"kind":"biometric_window","features":{"hr_mean":100,"hrv_mean":25}})` wrapped in a `MessageEnvelope(meta_context=MetaContext.SLEEP, consent_scope="apple_health_v1", trace_id=...)`. Assert the **belief-envelope** propagation (`out.trace_id == inbound.trace_id`, `out.meta_context == MetaContext.SLEEP`, `out.consent_scope == "apple_health_v1"`, `out.source_role == role_for("L3.fusion")`); assert `belief.get("arousal_inferred", now=now)` is not None and its `value` keys are the **axis output** (`arousal`/`band`/`hr_mean`), with `est.meta_context is None` on the estimate; and confirm the same biometric packet leaves `audio_social_context`/`affect_prosody`/`visual_context`/`cognitive_load` OFFLINE (mirrors `test_live_audio_packet_fuses_social_belief_no_db`'s OFFLINE-for-non-matching assertions). This also documents arousal firing under SLEEP (and, with a WAKING variant, under both frames).

**Suite dir to append:** new tests land under `fusion/` (`fusion/axes/test_*.py` + `fusion/test_participant.py`), already covered by the CI invocation.

**Exact CI command** (from `apps/inference`, no `DATABASE_URL`):
```
PYTHONDONTWRITEBYTECODE=1 python -m pytest core sensors features fusion prediction decision output bci -q
```

## Commitments touched

- **#14 (meta-context biases every layer)** — HONORED by honest deferral, not fake gating. `arousal_inferred` computes unconditionally and tags `meta_context=None` because the packet genuinely lacks the frame; raw components exposed so L4/L5 (which hold the envelope) reinterpret exertion-vs-sleep-arousal. `affect_prosody` stamps `"waking"` like its siblings. "No inference during deep sleep" suppression defers to L5/L6 — same convention-not-code status as cognitive_load/visual_context. Faking a waking-vs-sleep branch from a `None` hint would be exactly the dishonesty the posture forbids.
- **#1 (i_model_id propagation)** — INHERIT the tracked gap. Both axes set `AxisEstimate.i_model_id=None` like every existing axis; envelope i_model_id rides through `forward_envelope`. Do not advance it as a one-off (fills with clustering).
- **#9 (transport-agnostic / contract early) + #16 (scaffolds feed the flywheel)** — both axes land as honest per-axis scaffolds composing forward toward the JEPA latent world model: `arousal_inferred` from real biometric signal; `affect_prosody` draining a currently-WASTED real prosody stream into belief logging. Documented in each docstring per the cognitive_load/visual_context precedent.
- **#11 (semantic-first)** — satisfied by construction: both axes consume already-extracted feature dicts (HR/HRV scalars; prosody floats), never raw waveform/pixels.
- **Honesty over theater** — `state_declared` DEFERRED rather than shipped as a perpetually-OFFLINE shell; `valence` DOWNGRADED to an honestly-labeled prosodic-arousal proxy (`valence_discriminating=False`) rather than a fabricated number; arousal's #14 branch NOT faked from a `None` hint; `hr_pct_above_baseline` removed from the scalar (honest math to match the honest label).

## Risks / notes

- **Calibration placeholders.** `HR_LO/HI=55/110`, `HRV_LO/HI=20/70`, weights `0.6/0.4` are documented placeholders awaiting the real-watch/EXG-Pill calibration step — same status as cognitive_load's `_ENGAGE_LO/_HI`. Fine for now (deferred per the rebuild posture; no real-data run gated on them).
- **No personal baseline.** Arousal is population-style, NOT personalized "deviation from your norm" — the empath framing's personal baseline source does not exist on the bus yet. The value/method/confidence/`baseline="in_window_only"` tags all say so honestly. A personal-baseline source (e.g. resting HR/HRV from the 10yr Apple Health import) is net-new and out of scope.
- **`affect_prosody` is arousal, not valence.** True valence is explicitly deferred (docstring). Any downstream consumer must honor `valence_discriminating=False`.
- **`state_declared` is a separate future piece.** When built: NEW L1 EXPLICIT producer in `voice/loop.py` (first-ever `intent=EXPLICIT` emission) + NEW L2 LLM affect classifier (`ChatClient.chat_structured` → `{category, valence, arousal, confidence}`; honest because it handles negation/sarcasm a lexicon mangles, and explicit utterances are low-frequency so per-call LLM cost is trivial) dropping raw words per #11 + a short-`fresh_for_seconds` L3 axis (a self-report decays fast — must not keep a 9am "I'm anxious" fresh at 3pm). It is HIGH confidence (ground-truth self-report = the training label the inferred axes are graded against) and the raw sentence is arguably worth KEEPING as memory (`regis_observations`, observer precedent) — two consumers of one explicit event. The 0009 "reservation" is only a doc-comment with no CHECK/enum enforcement, which strengthens the case for a dedicated multi-layer build, not an L3-only shell.
