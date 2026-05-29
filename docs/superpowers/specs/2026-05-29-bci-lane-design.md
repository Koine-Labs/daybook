# BCI Lane Design — synthetic EEG → band-power → cognitive_load (L1→L2→L3)

**Date:** 2026-05-29
**Branch context:** authored on `feat/fill-l6-composer` working tree; intended as a standalone fill of the BCI lane.
**Goal:** Build the full BCI software lane on **synthetic EEG** so the BioAmp EXG Pill (single-channel biopotential amp, ~10 days out) is **plug-and-play on arrival — a calibration task, not a from-scratch build.** Today `Modality.BCI` is enum-only (`"bci"` in `core/protocol/enums.py`); the L2 registry points `"bci"` at the passthrough stub; there is no L3 `cognitive_load` axis. This spec fills all three layers + a reusable band-power module + an off-CI firmware/Pi stub.

**Verified baseline:** `python -m pytest core sensors features fusion prediction decision output -q` → **180 passed in ~6.7s** (run from `apps/inference`, no `DATABASE_URL`). scipy **1.17.1** + numpy **2.4.6** present in `.venv` and are base deps (CI installs `-r pyproject.toml --extra dev`). New tests must hold the suite green and add to that count.

**Frozen, MUST NOT change:** `core/protocol/*` (enums, `SignalPacket`/`FeatureSnapshot`/`AxisEstimate`/`BeliefState` shapes), the `Transport` ABC, the 6 topics (`l1.signal` … `l6.output`). All deliverables compose *behind* those frozen contracts.

**Scope (YAGNI):** `cognitive_load` only. `arousal`/`valence` band-power axes are a documented FOLLOW-ON, not built here.

---

## 0. Layer-by-layer summary (what gets built)

| # | Deliverable | New file(s) | Mirrors |
|---|---|---|---|
| 1 | Band-power function (pure numpy/scipy) | `bci/__init__.py`, `bci/bandpower.py`, `bci/test_bandpower.py` | n/a (new canonical math, like `classifier/features.py` is for biometric) |
| 2 | L1 synthetic EEG producer + raw generator | `sensors/eeg_adapter.py`, `sensors/test_eeg_adapter.py` | `sensors/audio_adapter.py` (AudioBusSink) |
| 3 | L2 BCI extractor | `features/bci.py`, `features/test_bci.py`; edit `features/participant.py` | `features/biometric.py` + `features/audio_social.py` |
| 4 | L3 `cognitive_load` axis | `fusion/axes/cognitive_load.py`, `fusion/axes/test_cognitive_load.py`; edit `fusion/participant.py` + `fusion/test_participant.py` | `fusion/axes/audio_social_context.py` (`fuse_from_feature` live pattern) |
| 5 | Consent scope for BCI | edit `consent.py` + `sensors/participant.py` (+ test) | existing `_MODALITY_CONSENT` map |
| 6 | Firmware/Pi stub (off CI) | `bci/firmware/eeg_edge_stub.py` (+ README note) | `AI_PI_CONTRACT.md` sensor packet shape |
| 7 | End-to-end arc test | `bci/test_bci_lane_arc.py` | `fusion/test_participant.py::test_live_audio_packet_fuses_social_belief_no_db` |

No change to `core/nodes.py`: L2 BCI extraction runs under the existing `L2.features` role; the `cognitive_load` axis runs under the existing `L3.fusion` role. No change to `core/protocol/decode.py`: `signal_from_dict` decodes any SignalPacket generically by `modality`/`intent`/`kind`/`payload`, so an `eeg_bandpower` packet rides `NetworkTransport` with **zero codec changes** (verified in `core/protocol/decode.py:29-33`).

---

## 1. Verified patterns this mirrors + the consent-scope gap

### L1 producer pattern (verified `sensors/`)
- `sensors/contract.py` — `IntentTaggedReading` is the modality+intent envelope (#10). `__post_init__` validates `modality ∈ {m.value for m in Modality}` (so `"bci"` is already a legal modality, no enum change) and `intent ∈ Intent`. `.to_signal_packet()` converts to the L1→L2 `SignalPacket`.
- `sensors/participant.py` — `emit(bus, reading, *, meta_context=UNKNOWN)` builds a fresh L1 envelope (new `trace_id`, `consent_scope` chosen by `consent_scope_for`) and publishes on `TOPIC_SIGNAL`. `consent_scope_for` special-cases `source.startswith("mac.")`, else looks up `_MODALITY_CONSENT[modality]`, else `DEFAULT_CONSENT_SCOPE = "unscoped_v0"`.
- `sensors/audio_adapter.py` — `AudioBusSink(bus, *, user_id, meta_context)`: transport-agnostic (holds only a `MessageBus`), builds `IntentTaggedReading(modality=AUDIO, intent=CONTINUOUS, ...)` and calls `emit`. **This is the exact shape the EEG producer mirrors** (modality=BCI instead of AUDIO).

### L2 extractor pattern (verified `features/`)
- `features/participant.py` — `EXTRACTORS: dict[str, Extractor]` keyed by `Modality` value; `"bci"` currently → `_stub_passthrough_extractor`. Real extractors register by replacing the value on the same key (the comment names this exact seam). `extract(sig)` runs `select_extractor(sig.modality)(sig)`; the bus handler publishes the resulting `FeatureSnapshot` on `TOPIC_FEATURE`.
- `features/biometric.py` — the real-extractor precedent: structured payload (`{kind, extractor, feature_cols, features, vector, ...}`), provenance tag (`EXTRACTOR_TAG = "biometric_rem_features.v1"`), reuses canonical math (`classifier.features.compute_session_features`) rather than reimplementing. **The BCI extractor mirrors this: reuse `bci.bandpower.compute_band_powers`, emit a structured payload + `EXTRACTOR_TAG`.**
- `features/audio_social.py` — shows the lighter "derived features keyed in payload + `social_category` helper" style the L3 live-fuse reads. The BCI extractor's derived features (theta/beta ratio, engagement index) are keyed into `payload["features"]` the same way `social_category` is keyed in.

### L3 axis pattern (verified `fusion/`)
- `fusion/axes/audio_social_context.py` — **the just-built live-fusion pattern to MIRROR.** `fuse_from_feature(packet, *, now)` returns an `AxisEstimate` **only for its own kind** (`feats.get("kind") != "audio_social_context"` → `None`, so other packets fall through to DB), with no DB import in the live path; `fuse_recent(...)` is the DB fallback. `cognitive_load` mirrors `fuse_from_feature` exactly; its DB fallback is intentionally **omitted** (see §5 — there is no `eeg_bandpower` sensor table yet).
- `fusion/participant.py` — `AXIS_REGISTRY` (the "three live axes": `meta_context`, `sleep_stage`, `audio_social_context`). `_audio_combiner(packet, now)` is the **live-first** pattern: try `fuse_from_feature`; if `None`, fall to DB `fuse_recent`; any exception → `_offline_estimate` (never crashes the bus). `_wrap_fuse_recent` is the DB-only adapter. **`cognitive_load` registers as a live-only combiner** (`fuse_from_feature` only, exception-guarded to OFFLINE) — count goes **3 → 4**.
- `fusion/belief_state.py` — `AxisEstimate(axis, value: dict, timestamp, confidence, source, meta_context, i_model_id, fresh_for_seconds)`. `value` is a free-form dict. `is_fresh` gates on `(now - timestamp) <= fresh_for_seconds`. `BeliefState.update` replaces by axis; `snapshot` exposes only fresh axes.

### The consent-scope gap (verified — must close)
`consent.py::CONSENT_SCOPES` has `mac`/`hk`/`voice` live and a **commented-out** reservation: `# "eeg": "eeg_continuous_v1",   # reserved — BioAmp EXG Pill onboarding`. And `sensors/participant.py::_MODALITY_CONSENT` has **no `Modality.BCI` entry**, so a BCI reading today silently falls back to `DEFAULT_CONSENT_SCOPE = "unscoped_v0"`. That is dishonest for a privacy-sensitive neural stream.

**Fix (small, additive):**
1. In `consent.py`, uncomment/add `"eeg": "eeg_continuous_v1"` to `CONSENT_SCOPES`.
2. In `sensors/participant.py::_MODALITY_CONSENT`, add `Modality.BCI.value: CONSENT_SCOPES["eeg"]`.
3. Test: a BCI `IntentTaggedReading` emitted via `sensors.participant.emit` rides under `consent_scope == "eeg_continuous_v1"` (assert on the returned envelope's `consent_scope`), proving it is no longer `unscoped_v0`.

This is the only change touching the consent registry; it is additive and matches the reserved naming already written in the file.

---

## 2. Band-power module — `bci/bandpower.py`

Pure numpy/scipy. **The edge (Pi) computes band-powers from raw ADC windows; raw EEG is discarded at the edge and NEVER rides the bus** (semantic-first, #11). This module is the reusable function both the firmware stub and the test harness call.

### Method
- **Spectral estimator:** Welch's method via `scipy.signal.welch` (PSD, `density` scaling, V²/Hz). Welch (averaged periodograms over overlapping segments) is the standard, low-variance choice for short single-channel EEG windows and is robust to the noise the EXG Pill will carry. numpy FFT is the fallback only if a dependency-minimal path is ever needed; Welch is the primary.
- **Window:** default analysis window **2.0 s** at sample rate **`fs` (default 256 Hz)** → 512 samples. Welch segment length `nperseg = min(len(x), fs)` (≈1 s, 50% overlap via default `noverlap=nperseg//2`), giving ~1 Hz frequency resolution — fine enough to separate the five bands. The window length is a parameter, not hardcoded into the bands.
- **Band integration:** integrate the PSD over each band's [f_lo, f_hi) using `np.trapz` (trapezoidal) on the masked frequency bins → **absolute band power** (V²). **Relative band power** = band_abs / total_abs over [delta_lo, gamma_hi) (the analysis band 0.5–45 Hz), so relatives sum to ≈1.0 across the five bands.

### Bands (Hz) — standard clinical EEG
| band | range (Hz) |
|---|---|
| delta | 0.5 – 4 |
| theta | 4 – 8 |
| alpha | 8 – 13 |
| beta | 13 – 30 |
| gamma | 30 – 45 |

(45 Hz upper bound keeps clear of 50/60 Hz mains; a notch is a firmware concern, documented in §6, not this function's job.)

### API + output shape
```python
# bci/bandpower.py
BANDS: dict[str, tuple[float, float]] = {
    "delta": (0.5, 4.0), "theta": (4.0, 8.0), "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0), "gamma": (30.0, 45.0),
}
DEFAULT_FS = 256.0

def compute_band_powers(samples: Sequence[float], *, fs: float = DEFAULT_FS) -> dict[str, Any]:
    """Welch PSD of a 1-D EEG window -> absolute + relative band powers.

    Returns:
      {
        "absolute": {"delta": float, "theta": ..., "gamma": float},  # V^2
        "relative": {"delta": float, ..., "gamma": float},           # sum ~= 1.0
        "total_power": float,                                         # V^2 over 0.5-45 Hz
        "dominant_band": "alpha",                                     # argmax of absolute
        "fs": 256.0, "n_samples": 512, "method": "welch", "version": "bandpower.v1",
      }
    """
```
- Defensive: `n_samples < 2*fs/delta_lo` (too short to resolve delta) or all-zero input → bands present with `0.0` powers and `dominant_band=None`, `total_power=0.0` (honest, never crashes — mirrors the "never fabricate" discipline in `features/biometric.py`). NaN/inf samples are rejected (raise `ValueError` — bad input is a bug, not a degraded state).
- No DB, no bus, no I/O. Importable with no `DATABASE_URL`.

### How synthetic test signals validate it (`bci/test_bandpower.py`)
All signals generated with numpy at `fs=256`, length ≥ 2 s, seeded RNG for noise. Assertions are on **relative** power (scale-invariant):
1. **10 Hz sinusoid → alpha dominates.** `dominant_band == "alpha"`; `relative["alpha"] > 0.5` and `> every other band`.
2. **6 Hz sinusoid → theta dominates** (`dominant_band == "theta"`).
3. **2 Hz sinusoid → delta dominates**; **22 Hz → beta**; **40 Hz → gamma** (parametrized).
4. **Sum of relatives ≈ 1.0** (`abs(sum - 1.0) < 1e-6`) for any in-band signal.
5. **Two-tone (10 Hz + 22 Hz equal amplitude) → alpha and beta both elevated**, each `> delta`, and the two together hold the majority of relative power.
6. **Amplitude scaling invariance:** multiplying samples by 5× leaves *relative* powers unchanged (within 1e-6) while *absolute* total_power scales ~25×.
7. **Degraded inputs:** all-zeros → all powers `0.0`, `dominant_band is None`, no crash; a 5-sample window → degraded zero result, no crash.
8. **Pure white noise → no single band holds a large majority** (sanity: `max(relative.values()) < 0.6`), guarding against a bug that always reports one band.

---

## 3. L1 EEG producer + synthetic generator — `sensors/eeg_adapter.py`

Mirrors `sensors/audio_adapter.py`. Transport-agnostic (holds only a `MessageBus`), so the *same* class works over `InProcessTransport` (synthetic on the Mac today) and `NetworkTransport` (Pi later) with no change.

### Synthetic raw-EEG generator (pure numpy, test + local-run only)
```python
def synthesize_eeg_window(
    *, fs: float = 256.0, seconds: float = 2.0,
    band_mix: dict[str, float] | None = None,   # band -> amplitude (uV); default alpha-dominant
    noise_uv: float = 2.0, seed: int | None = None,
) -> np.ndarray:
    """Sum of band-center sinusoids + Gaussian noise -> a 1-D raw EEG window (uV)."""
```
- Default `band_mix` is alpha-dominant (relaxed-waking), so the default arc lands a recognizable `cognitive_load` value. A `theta`-heavy / `beta`-heavy mix is selectable for tests asserting load direction.
- **This is the only place a "raw" waveform exists in tests.** It is consumed by `compute_band_powers` and then discarded — it never becomes a payload, mirroring the edge-discard rule.

### Producer
```python
class EEGBusSink:
    """Emits eeg_bandpower SignalPackets onto a MessageBus. Raw EEG never rides the bus."""
    KIND = "eeg_bandpower"
    EEG_SOURCE = "eeg_edge_v1"   # real Pi sets source='esp32_bioamp_pill' per AI_PI_CONTRACT

    def __init__(self, bus, *, user_id=DEFAULT_USER_ID, fs=256.0,
                 meta_context: MetaContext = MetaContext.UNKNOWN): ...

    def write_window(self, *, user_id: str, recorded_at: datetime, samples) -> None:
        """Compute band powers from a raw window, discard the raw, emit a semantic packet."""
        bp = compute_band_powers(samples, fs=self.fs)
        reading = IntentTaggedReading(
            modality=Modality.BCI.value, intent=Intent.CONTINUOUS.value,
            kind=self.KIND, payload=self._payload(bp),
            source=self.EEG_SOURCE, timestamp=recorded_at, user_id=user_id)
        emit(self.bus, reading, meta_context=self.meta_context)

    def emit_band_powers(self, *, user_id, recorded_at, band_powers: dict) -> None:
        """Edge variant: the Pi already computed band powers; emit them directly (no raw)."""
```
- `_payload(bp)` shape (semantic-first — **band powers + derived only, no samples**):
  ```python
  {
    "absolute": {...}, "relative": {...}, "total_power": float,
    "dominant_band": str | None, "fs": 256.0, "n_samples": int,
    "channel": "single", "method": "welch", "bandpower_version": "bandpower.v1",
  }
  ```
- `emit_band_powers` is the path the real Pi firmware uses (it computes band-powers on-device and ships only the semantic dict). `write_window` is the convenience path for the Mac-side synthetic harness; both produce an identical packet shape.
- Producer tests (no DB — `emit` builds a fresh envelope, publishes on a bare `MessageBus`): assert the published envelope has `payload.modality == "bci"`, `payload.intent == "continuous"`, `payload.kind == "eeg_bandpower"`, the payload carries `relative`/`absolute`/`dominant_band` and **no raw `samples` key**, and `consent_scope == "eeg_continuous_v1"` (proves §1 consent fix end-to-end through `emit`).

---

## 4. L2 BCI extractor — `features/bci.py`

Registered for `"bci"` in `features/participant.py::EXTRACTORS`, **replacing** `_stub_passthrough_extractor`. Mirrors `features/biometric.py` (structured payload + `EXTRACTOR_TAG`, reuses canonical math — here the band-power dict is already computed at L1, so L2 derives the higher-order features).

```python
# features/bci.py
EXTRACTOR_TAG = "bci_bandpower_features.v1"

def extract(sig: SignalPacket) -> FeatureSnapshot:
    p = dict(sig.payload)
    relative = p.get("relative", {}) or {}
    absolute = p.get("absolute", {}) or {}
    derived = compute_derived(relative, absolute)   # theta/beta ratio, alpha power, engagement index
    return FeatureSnapshot(
        user_id=sig.user_id, timestamp=sig.timestamp,
        modality=sig.modality, source=sig.source,
        payload={
            "kind": sig.kind,                       # "eeg_bandpower"
            "extractor": EXTRACTOR_TAG,
            "bands_relative": relative,
            "bands_absolute": absolute,
            "dominant_band": p.get("dominant_band"),
            "features": derived,                    # the L3-consumable derived dict
        },
        intent=sig.intent if sig.intent in _INTENT_VALUES else _DEFAULT_INTENT,
        confidence=sig.confidence, i_model_id=sig.i_model_id,
    )
```

### Derived features (`compute_derived`) — the L3-consumable contract
All computed from **relative** band power (scale-invariant, robust to single-channel gain drift). Division guards: any denominator `<= eps (1e-9)` → that feature is `None` (honest; never `inf`). Returned dict:
| feature | formula | meaning |
|---|---|---|
| `theta_beta_ratio` | `theta / beta` | classic drowsiness / low-engagement marker; **high → low load/drowsy** |
| `alpha_power` | `alpha` (relative) | relaxed-but-awake; high alpha → idling cortex |
| `engagement_index` | `beta / (alpha + theta)` | Pope engagement index; **high → high cognitive engagement/load** |
| `beta_rel` | `beta` (relative) | passthrough convenience for the axis |

`compute_derived` lives in `features/bci.py` as a free function (single source of truth, mirroring `audio_social.social_category`) and is what the L3 axis reads — the axis does **not** re-derive from raw bands.

L2 tests (`features/test_bci.py`): feed a synthetic `SignalPacket(modality="bci", kind="eeg_bandpower", payload=<bandpower dict from compute_band_powers on a known signal>)`; assert the `FeatureSnapshot.payload` carries `extractor == EXTRACTOR_TAG`, `bands_relative` summing ≈1, and a `features` dict with finite `theta_beta_ratio`/`engagement_index`; assert a **beta-heavy** synthetic window yields higher `engagement_index` than a **theta-heavy** one; assert `select_extractor("bci") is features.bci.extract` (registry wiring) — the analog of the biometric registry assertion.

---

## 5. L3 `cognitive_load` axis — `fusion/axes/cognitive_load.py`

A v1 **HEURISTIC scaffold** (not a trained model) that maps band-power derived features → a `cognitive_load` `AxisEstimate`. `cognitive_load` is a **WAKING sub-context signal (#14)** and a v1 scaffold feeding the data flywheel toward the JEPA-era model (#16) — **honest provenance says exactly this.**

### Heuristic (exact formula)
Input: the L2 `features` dict (`engagement_index`, `theta_beta_ratio`, `alpha_power`). Primary driver is the **engagement index** (Pope), with the theta/beta ratio as a corroborating drowsiness signal.

```python
AXIS = "cognitive_load"
SOURCE = "L3.fusion.cognitive_load.v1_heuristic"
FRESH_SECONDS = 120          # EEG state shifts fast; matches meta_context's 120s, < sleep_stage's 600s

# v1 normalization constants (documented placeholders — NOT fitted).
# engagement_index = beta/(alpha+theta); empirical waking range ~0.1 (idle) .. ~1.2 (focused).
_ENGAGE_LO, _ENGAGE_HI = 0.15, 1.0

def _load_scalar(features) -> float | None:
    e = features.get("engagement_index")
    if e is None:
        return None
    # linear clamp into [0,1]; high engagement -> high load
    return max(0.0, min(1.0, (e - _ENGAGE_LO) / (_ENGAGE_HI - _ENGAGE_LO)))

def _band(load: float) -> str:
    return "low" if load < 0.34 else ("medium" if load < 0.67 else "high")
```

### Value shape + estimate
```python
def fuse_from_feature(packet, *, now=None) -> AxisEstimate | None:
    feats = getattr(packet, "payload", {}) or {}
    if feats.get("kind") != "eeg_bandpower":      # only our kind; else None (fall-through)
        return None
    derived = feats.get("features", {}) or {}
    load = _load_scalar(derived)
    if load is None:                               # no usable engagement signal -> OFFLINE upstream
        return None
    return AxisEstimate(
        axis=AXIS,
        value={
            "load": round(load, 3),                # [0,1] scalar
            "band": _band(load),                   # "low" | "medium" | "high"
            "engagement_index": derived.get("engagement_index"),
            "theta_beta_ratio": derived.get("theta_beta_ratio"),
            "method": "engagement_index_linear_v1",
            "scaffold": True,                       # explicit: not a trained model
        },
        timestamp=getattr(packet, "timestamp", None) or now or datetime.now(timezone.utc),
        confidence=0.4,                             # low — honest for an unfitted heuristic
        source=SOURCE,
        meta_context="waking",                      # cognitive_load is a WAKING sub-context (#14)
        fresh_for_seconds=FRESH_SECONDS,
        # i_model_id left None (commitment #1 hook present in AxisEstimate)
    )
```
- **Honest provenance:** `source="L3.fusion.cognitive_load.v1_heuristic"`, `value["scaffold"]=True`, `value["method"]="engagement_index_linear_v1"`, `confidence=0.4`. The module docstring states verbatim: *"v1 heuristic scaffold (engagement-index linear map). NOT a trained classifier. Normalization constants are documented placeholders, not fitted. This axis exists to generate the data flywheel toward the JEPA-era latent world model (commitment #16); it is a stand-alone per-axis scaffold per ARCHITECTURE §2.16's v1 plan, designed to compose forward, not be thrown away."*
- **No DB fallback `fuse_recent`** is provided: there is no `eeg_bandpower` sensor-table persistence path yet, and inventing one would be dishonest scope creep. The axis is **live-only** — exactly the `audio_social_context.fuse_from_feature`-only subset. (A DB `fuse_recent` is a documented follow-on for when EEG band-powers are persisted to `sensor_readings`.)

### Registry wiring (`fusion/participant.py`)
Add a live-only combiner mirroring `_audio_combiner` but without the DB branch:
```python
from .axes import audio_social_context, cognitive_load, meta_context, sleep_stage

def _cognitive_load_combiner(packet, now):
    try:
        return cognitive_load.fuse_from_feature(packet, now=now)   # live-only; None -> OFFLINE upstream
    except Exception as exc:  # noqa: BLE001 — never crash the bus
        return _offline_estimate("cognitive_load", now=now, reason=f"axis error: {exc!r}")

AXIS_REGISTRY = {
    "meta_context": _wrap_fuse_recent("meta_context", meta_context.fuse_recent),
    "sleep_stage": _wrap_fuse_recent("sleep_stage", sleep_stage.fuse_recent),
    "audio_social_context": _audio_combiner,
    "cognitive_load": _cognitive_load_combiner,
}
```
Behavioral consequence (consistent with the existing design): for a non-EEG packet (e.g. an audio packet), `cognitive_load.fuse_from_feature` returns `None`, the combiner returns `None`, and the participant records `cognitive_load` as an **OFFLINE** sentinel — exactly how `meta_context`/`sleep_stage` already degrade for an audio packet. The comment "Registry of the three live axes" updates to "four live axes."

### The 3 → 4 live-axis test update (`fusion/test_participant.py`) — honest
The existing assertion at `fusion/test_participant.py:114-117`:
```python
def test_default_registry_references_three_live_axes():
    assert set(P.AXIS_REGISTRY) == {"meta_context", "sleep_stage", "audio_social_context"}
```
becomes (rename + add the fourth):
```python
def test_default_registry_references_four_live_axes():
    assert set(P.AXIS_REGISTRY) == {
        "meta_context", "sleep_stage", "audio_social_context", "cognitive_load"
    }
```
The companion `test_live_audio_packet_fuses_social_belief_no_db` (lines 152-171) stays green: an audio packet now *also* yields an OFFLINE `cognitive_load` estimate; its existing assertions on `audio_social_context`/`meta_context`/`sleep_stage` are unaffected. Add one line asserting `belief.get("cognitive_load", now=now) is None` (OFFLINE never fresh) to document the new axis's degraded behavior for non-EEG packets.

### Axis unit tests (`fusion/axes/test_cognitive_load.py`) — no DB
Mirror `test_audio_social_context.py`'s `fuse_from_feature` block:
- beta-heavy synthetic-derived features → `band in {"medium","high"}`, `0 <= load <= 1`, `source` endswith `v1_heuristic`, `meta_context == "waking"`, `value["scaffold"] is True`, `confidence == 0.4`.
- theta-heavy / low-engagement features → `band == "low"`, lower `load` than the beta-heavy case.
- non-EEG kind (`kind="mac_activity"`) → `fuse_from_feature(...) is None`.
- missing `engagement_index` → `None` (degrades to OFFLINE upstream, never fabricates).

---

## 6. Firmware / Pi stub (off CI path) — `bci/firmware/eeg_edge_stub.py`

A documented, **off-CI** reference implementation of the ADC → band-power → emit contract, ready for the EXG Pill. It is NOT collected by the CI pytest paths (`core sensors features fusion prediction decision output`) — it lives under `bci/firmware/` which is outside those dirs — and imports the real `bci.bandpower.compute_band_powers` + `sensors.eeg_adapter.EEGBusSink` so it shares the exact semantic contract.

### Edge loop (pseudocode the real ESP32/Pi fills)
```
loop @ window cadence (e.g. every 1.0s, 2.0s window, 50% overlap):
    raw = adc.read_window(fs=256, seconds=2.0)        # EXG Pill -> ADC -> int16 buffer
    raw = notch_50_60(raw); raw = bandpass_0p5_45(raw)# mains + out-of-band rejection (firmware DSP)
    bp  = compute_band_powers(raw, fs=256)            # SEMANTIC extraction at the edge
    del raw                                           # RAW DISCARDED — never leaves the device
    sink.emit_band_powers(user_id=UID, recorded_at=now_utc(), band_powers=bp)  # only semantics on bus
```
- On the real rig, `sink` is an `EEGBusSink` bound to a **`NetworkTransport`-backed bus** so band-power packets travel ESP32→Pi(hub)→DESKTOP_COMPUTE; the stub binds an `InProcessTransport` bus and a synthetic generator so it runs on a laptop with no hardware.

### AI_PI_CONTRACT alignment (and the one additive proposal)
- `AI_PI_CONTRACT.md` already reserves EEG: its `kind` enum lists `eeg_alpha`/`eeg_beta`/`eeg_theta` with payload `{"microvolts": ..., "unit": "uV"}`, and its prose says EEG bands are *future* — *"emit them now if available, but the v0 classifier ignores them."* This BCI lane is the consumer that stops ignoring them.
- **Alignment note (documented in the stub + a one-line contract addendum):** the per-band-microvolt row format is the *raw-ish* legacy shape. The nervous-system bus instead carries **one consolidated `eeg_bandpower` semantic packet** (all five bands' absolute+relative power + derived) per window — strictly more semantic-first (#11) than five separate microvolt rows, and it matches the `SignalPacket(modality=BCI, kind="eeg_bandpower")` the lane consumes. The contract's `source` field maps to `EEGBusSink.EEG_SOURCE` (real Pi: `"esp32_bioamp_pill"`). This is an **additive minor-version** note to AI_PI_CONTRACT (no breaking change; the legacy per-band kinds remain documented), to be appended when the Pi chat wires the producer.
- The stub documents the open hardware questions it inherits from the contract (sampling rate vs the EXG Pill's analog bandwidth, notch frequency 50 vs 60 Hz, transport serial-vs-WiFi) as TODOs for the hardware chat — the AI side stays agnostic, exactly as the contract states.

### Calibration-on-arrival path (why this is "plug-and-play, a calibration task")
When the EXG Pill arrives: (1) point the stub's ADC reader at the real device, (2) record a few labeled waking windows (idle vs focused) to **fit** `_ENGAGE_LO`/`_ENGAGE_HI` (today's documented placeholders) — replacing the constants is the *only* numerical calibration step; the entire L1→L2→L3 plumbing, contracts, and tests are already in place and green.

---

## 7. Test plan — hardware-free, network-free, DB-free, on the CI path

All new tests live under the CI-collected dirs (`bci/`, `sensors/`, `features/`, `fusion/`) and run with **no `DATABASE_URL`**. The CI-mirror command is unchanged:
```
cd apps/inference && python -m pytest core sensors features fusion prediction decision output -q
```
(Note: `bci/` is NOT in that path list. To keep BCI unit tests on CI, add `bci` to the pytest invocation in `.github/workflows/ci.yml` **and** to the CI-mirror command — a one-token additive edit: `... output bci -q`. The firmware stub under `bci/firmware/` carries no `test_*.py`, so it is never collected. This ci.yml edit is the single CI-config change in this spec and must be called out in the PR.)

### Tier 1 — band-power on known sinusoids (`bci/test_bandpower.py`)
Per §2: 10 Hz→alpha, 6 Hz→theta, 2 Hz→delta, 22 Hz→beta, 40 Hz→gamma (parametrized); relatives sum≈1; two-tone elevates two bands; amplitude-scale invariance of relatives; degraded (zeros / too-short) → zero result no crash; white noise → no >0.6 majority. **No bus, no DB, no network.**

### Tier 2 — L1 producer + synthetic generator (`sensors/test_eeg_adapter.py`)
- `synthesize_eeg_window` returns a finite 1-D array of expected length; an alpha-mix window run through `compute_band_powers` is alpha-dominant (generator↔analyzer round-trip).
- `EEGBusSink.write_window` on a bare `MessageBus`: exactly one envelope published on `TOPIC_SIGNAL`; `payload.modality=="bci"`, `intent=="continuous"`, `kind=="eeg_bandpower"`; payload has `relative`/`absolute`/`dominant_band` and **no `samples`/raw key**; envelope `consent_scope=="eeg_continuous_v1"` (consent fix proven through the real `emit` path).
- `emit_band_powers` produces the identical packet shape from a pre-computed band-power dict (the Pi path).

### Tier 3 — consent (`sensors/test_sensors.py` addition or in `test_eeg_adapter.py`)
A BCI `IntentTaggedReading` through `sensors.participant.consent_scope_for` → `"eeg_continuous_v1"` (not `"unscoped_v0"`).

### Tier 4 — L2 extractor (`features/test_bci.py`)
Per §4: registry wiring (`select_extractor("bci") is features.bci.extract`); structured payload with `EXTRACTOR_TAG`, `bands_relative` sum≈1, finite derived features; beta-heavy window → higher `engagement_index` than theta-heavy; missing bands → derived features `None`, no crash.

### Tier 5 — L3 axis unit (`fusion/axes/test_cognitive_load.py`)
Per §5: beta-heavy → medium/high band; theta-heavy → low band with lower load; non-EEG kind → `None`; missing engagement → `None`; provenance fields (`scaffold=True`, `confidence=0.4`, `meta_context="waking"`, source endswith `v1_heuristic`).

### Tier 6 — full lane arc, synthetic EEG → L1 → L2 → L3 belief (`bci/test_bci_lane_arc.py`)
The headline integration test, mirroring `fusion/test_participant.py::test_live_audio_packet_fuses_social_belief_no_db` (DEFAULT registry, **NO DB, NO network, NO hardware**):
```
bus = MessageBus()
captured_beliefs = []; bus.subscribe(TOPIC_BELIEF, captured_beliefs.append)
features.participant.register(bus)          # L2: real EXTRACTORS incl. bci.extract
fusion.participant.register(bus)            # L3: real AXIS_REGISTRY incl. cognitive_load
sink = EEGBusSink(bus, meta_context=MetaContext.WAKING)   # L1
samples = synthesize_eeg_window(band_mix=<beta-heavy / focused>, seed=0)
sink.write_window(user_id=USER, recorded_at=now, samples=samples)  # raw computed+discarded at L1

# Assert the belief arc:
belief = captured_beliefs[-1]
est = belief.get("cognitive_load", now=now)
assert est is not None and 0.0 <= est.value["load"] <= 1.0 and est.value["band"] in {"low","medium","high"}
assert est.value["scaffold"] is True and est.source.endswith("v1_heuristic")
# DB-backed axes degrade to OFFLINE for an EEG packet (no DB touched):
assert belief.get("meta_context", now=now) is None
assert belief.get("sleep_stage", now=now) is None
# Trace preserved end-to-end; envelope serializes (wire-ready, NetworkTransport-safe):
assert captured_beliefs[-1].to_dict()  # round-trips
```
Add a second arc with a **theta-heavy/drowsy** window asserting the resulting `load` is lower / `band` trends `"low"` — proving the heuristic responds to band content, not just that it fires.

### Regression
After all additions: `python -m pytest core sensors features fusion prediction decision output bci -q` must report **180 + new tests passed**, with the renamed four-axis assertion green and every prior test still passing. No `core/protocol/*`, `Transport` ABC, or topic change.

---

## 8. File manifest (net-new + edits)

**New:**
- `bci/__init__.py`
- `bci/bandpower.py` — `compute_band_powers`, `BANDS`, `DEFAULT_FS`
- `bci/test_bandpower.py`
- `bci/firmware/__init__.py`, `bci/firmware/eeg_edge_stub.py` (off-CI; no test_*.py)
- `bci/test_bci_lane_arc.py`
- `sensors/eeg_adapter.py` — `EEGBusSink`, `synthesize_eeg_window`
- `sensors/test_eeg_adapter.py`
- `features/bci.py` — `extract`, `compute_derived`, `EXTRACTOR_TAG`
- `features/test_bci.py`
- `fusion/axes/cognitive_load.py` — `fuse_from_feature`, heuristic helpers
- `fusion/axes/test_cognitive_load.py`

**Edited (additive only):**
- `consent.py` — add `"eeg": "eeg_continuous_v1"` to `CONSENT_SCOPES`
- `sensors/participant.py` — add `Modality.BCI.value: CONSENT_SCOPES["eeg"]` to `_MODALITY_CONSENT`
- `features/participant.py` — `EXTRACTORS["bci"] = bci.extract` (replace passthrough stub); import `features.bci`
- `fusion/participant.py` — import `cognitive_load`; add `_cognitive_load_combiner`; register `"cognitive_load"`; comment "three" → "four" live axes
- `fusion/test_participant.py` — rename `test_default_registry_references_three_live_axes` → `...four...`, add `cognitive_load`; add OFFLINE-on-audio assertion
- `.github/workflows/ci.yml` — append `bci` to the pytest path list (single token); update the CI-mirror command in docs accordingly

**Frozen / untouched:** `core/protocol/*`, `core/bus/transport.py` (Transport ABC), the 6 topics, `core/nodes.py` (BCI reuses `L2.features` + `L3.fusion` roles), `core/protocol/decode.py` (generic SignalPacket decode covers `eeg_bandpower`).

---

## 9. Commitment alignment (audit anchors)
- **#10** Intent×Modality: BCI reading tagged `(CONTINUOUS, BCI)`; the lane routes by modality at L2 (BCI extractor) and feeds an intent-agnostic axis at L3.
- **#11** Semantic-first: raw EEG computed→discarded at the edge; only `eeg_bandpower` semantic packets ride the bus; the synthetic generator's waveform exists only inside the producer/test boundary.
- **#14** Meta-context bias: `cognitive_load` carries `meta_context="waking"` — a WAKING sub-context signal (no EEG-load inference during deep sleep is a downstream concern, not this axis's).
- **#15 / #16** JEPA destination: `cognitive_load` is a **stand-alone per-axis v1 scaffold** with honest `scaffold=True` provenance, generating the (state) half of the (state, action, next-state) flywheel; it composes forward into the world model's per-axis projection heads rather than being thrown away. No model is trained here.
- **#1** I-Model hook: `i_model_id` present (None) on `SignalPacket`, `FeatureSnapshot`, `AxisEstimate` throughout the lane.
