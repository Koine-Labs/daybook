"""L1 biometric producer — hardware-free, network-free, DB-free.

window_readings is a pure windower (tested against how features/biometric.py
._lag_value consumes hr_mean_history); synthesize_biometric_window is a
deterministic CI/demo generator; the end-to-end test drives a synthetic window
through WatchBusSink(meta_context=SLEEP) onto a real MessageBus and asserts the
full L1->L2->L4 REM arc with the real trained model (no DB, no network).
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from core.bus.bus import TOPIC_FEATURE, TOPIC_PREDICTION, TOPIC_SIGNAL, MessageBus  # noqa: E402
from core.protocol.enums import Intent, MetaContext, Modality  # noqa: E402
from core.protocol.envelope import MessageEnvelope  # noqa: E402
from core.protocol.payloads import FeatureSnapshot, Prediction, SignalPacket  # noqa: E402
from consent import CONSENT_SCOPES  # noqa: E402
from features import participant as features_participant  # noqa: E402
from features.biometric import (CONTEXT_SECONDS, EPOCH_SECONDS, FEATURE_COLS,  # noqa: E402
                                _lag_value)
from prediction import feature_participant as prediction_participant  # noqa: E402
from sensors.watch_adapter import (KIND_BIOMETRIC_WINDOW, WATCH_SOURCE,  # noqa: E402
                                   WatchBusSink, synthesize_biometric_window,
                                   window_readings)

BASE = datetime(2026, 5, 29, 3, 0, 0, tzinfo=timezone.utc)


def _flat_stream(*, n_epochs: int, hr_per_epoch: int = 3, hr0: float = 60.0,
                 hr_step: float = 5.0) -> list[dict]:
    """A time-ordered flat list spanning n_epochs of 30s, one hr_mean per epoch."""
    out: list[dict] = []
    for e in range(n_epochs):
        epoch_start = BASE + timedelta(seconds=EPOCH_SECONDS * e)
        for j in range(hr_per_epoch):
            out.append({
                "recorded_at": epoch_start + timedelta(seconds=j * 5),
                "kind": "heart_rate",
                "value": hr0 + hr_step * e,
            })
            out.append({
                "recorded_at": epoch_start + timedelta(seconds=j * 5 + 1),
                "kind": "hrv",
                "value": 40.0 + e,
            })
    return out


# ---- window_readings: epoch / context boundaries ------------------------------

def test_window_readings_yields_one_payload_per_epoch():
    readings = _flat_stream(n_epochs=4)
    windows = list(window_readings(readings, epoch_seconds=EPOCH_SECONDS,
                                   context_seconds=CONTEXT_SECONDS))
    assert len(windows) == 4
    for w in windows:
        assert "epoch_start_at" in w
        assert "readings" in w
        assert "hr_mean_history" in w
        assert isinstance(w["epoch_start_at"], datetime)
        assert w["epoch_start_at"].tzinfo is not None


def test_window_readings_carries_only_context_plus_epoch_window():
    # 12 epochs so the last epoch's context window (300s = 10 epochs) trims the
    # earliest readings: the window must NOT carry the whole stream.
    readings = _flat_stream(n_epochs=12)
    windows = list(window_readings(readings, epoch_seconds=EPOCH_SECONDS,
                                   context_seconds=CONTEXT_SECONDS))
    last = windows[-1]
    epoch_start = last["epoch_start_at"]
    lo = epoch_start - timedelta(seconds=CONTEXT_SECONDS)
    hi = epoch_start + timedelta(seconds=EPOCH_SECONDS)
    times = [r["recorded_at"] for r in last["readings"]]
    assert times, "window should not be empty"
    assert all(lo <= t < hi for t in times)
    # the very first reading (300s+ before the last epoch) is excluded
    assert min(times) > readings[0]["recorded_at"]


# ---- window_readings: hr_mean_history vs _lag_value ---------------------------

def test_hr_mean_history_matches_canonical_extractor_hr_mean():
    # The load-bearing invariant: each hr_mean_history entry equals the windowed
    # hr_mean the canonical L2 extractor computes for that prior epoch's window,
    # so _lag_value(history, k) == the lag the model trained on. We assert it
    # against compute_biometric_features run on each prior epoch's own window.
    from features.biometric import compute_biometric_features

    readings = _flat_stream(n_epochs=8, hr0=60.0, hr_step=5.0)
    windows = list(window_readings(readings, epoch_seconds=EPOCH_SECONDS,
                                   context_seconds=CONTEXT_SECONDS))
    hist = windows[7]["hr_mean_history"]
    assert len(hist) == 7  # one per prior epoch, oldest-first

    for i in range(7):
        canonical = compute_biometric_features(windows[i])["hr_mean"]
        assert hist[i] == pytest.approx(canonical), f"history[{i}] != epoch {i} hr_mean"

    # _lag_value reads history[-k]: lag1 is the immediately preceding epoch (index 6),
    # lag3 is index 4, lag5 is index 2 — monotone since this stream's HR rises.
    assert _lag_value(hist, 1) == hist[6]
    assert _lag_value(hist, 3) == hist[4]
    assert _lag_value(hist, 5) == hist[2]
    assert _lag_value(hist, 1) > _lag_value(hist, 5)


def _canonical_lag_columns(readings: list[dict]) -> "pd.DataFrame":
    """Run the real trainer extractor over the same stream, labels on every
    contiguous 30s epoch slot, so its hr_lag{1,3,5}_mean are the ground truth."""
    import pandas as pd

    from classifier.data import SessionBundle
    from classifier.features import compute_session_features

    norm = sorted(readings, key=lambda r: r["recorded_at"])
    first, last = norm[0]["recorded_at"], norm[-1]["recorded_at"]
    n_epochs = int((last - first).total_seconds() // EPOCH_SECONDS) + 1
    labels = pd.DataFrame(
        [{"epoch_start_at": pd.Timestamp(first + timedelta(seconds=EPOCH_SECONDS * e)),
          "stage": "REM"} for e in range(n_epochs)]
    )
    sensors = pd.DataFrame(
        [{"recorded_at": pd.Timestamp(r["recorded_at"]), "kind": r["kind"], "value": r["value"]}
         for r in norm]
    )
    bundle = SessionBundle(
        session_id="fidelity", user_id="",
        started_at=pd.Timestamp(first),
        ended_at=pd.Timestamp(last + timedelta(seconds=EPOCH_SECONDS)),
        duration_seconds=int((last + timedelta(seconds=EPOCH_SECONDS) - first).total_seconds()),
        sensors=sensors,
        labels=labels,
    )
    return compute_session_features(
        bundle, epoch_seconds=EPOCH_SECONDS, context_seconds=CONTEXT_SECONDS
    ).reset_index(drop=True)


def _gappy_stream() -> list[dict]:
    """HR present in epochs 0-4, a 12-epoch blackout (5-16), then HR resumes 17-22.
    The blackout exceeds the 300s context window, so a compacting history desyncs."""
    out: list[dict] = []
    for e in list(range(0, 5)) + list(range(17, 23)):
        es = BASE + timedelta(seconds=EPOCH_SECONDS * e)
        for j in range(3):
            out.append({"recorded_at": es + timedelta(seconds=5 * j),
                        "kind": "heart_rate", "value": 60.0 + e})
    return out


def test_gappy_stream_lags_match_canonical_positional_lags():
    # With an HR blackout longer than the context window, hr_mean_history must
    # advance one entry PER EPOCH (NaN for empty windows) so _lag_value(history, k)
    # stays positionally aligned with compute_session_features' hr_lag{1,3,5}_mean.
    # A compacting (skip-empty) history would desync the post-gap lags.
    import math

    readings = _gappy_stream()
    windows = list(window_readings(readings, epoch_seconds=EPOCH_SECONDS,
                                   context_seconds=CONTEXT_SECONDS))
    canon = _canonical_lag_columns(readings)
    assert len(windows) >= 23
    assert len(canon) >= len(windows)

    def eq(a: float, b: float) -> bool:
        return a == b or (math.isnan(a) and math.isnan(b))

    saw_post_gap_nan = False
    for i, w in enumerate(windows):
        hist = w["hr_mean_history"]
        c = canon.iloc[i]
        assert eq(_lag_value(hist, 1), float(c["hr_lag1_mean"])), f"epoch {i} lag1"
        assert eq(_lag_value(hist, 3), float(c["hr_lag3_mean"])), f"epoch {i} lag3"
        assert eq(_lag_value(hist, 5), float(c["hr_lag5_mean"])), f"epoch {i} lag5"
        if 17 <= i <= 18 and math.isnan(_lag_value(hist, 1)):
            saw_post_gap_nan = True
    # The first post-gap epoch's preceding epoch had no HR -> lag1 must be NaN,
    # the exact value the model trained on (a compacting history yields a stale number).
    assert saw_post_gap_nan, "post-gap lag1 should surface the canonical NaN, not a stale value"


def test_nan_and_missing_values_dropped_like_canonical_extractor():
    # A NaN/None/missing-'value' reading must be dropped before averaging (mirroring
    # features.biometric._parse_window) and never crash — so an epoch with one clean
    # 60.0 reading plus a NaN yields hr_mean 60.0, not NaN, in hr_mean_history.
    import math

    readings = [
        {"recorded_at": BASE, "kind": "heart_rate", "value": 60.0},
        {"recorded_at": BASE + timedelta(seconds=5), "kind": "heart_rate", "value": float("nan")},
        {"recorded_at": BASE + timedelta(seconds=10), "kind": "heart_rate", "value": None},
        {"recorded_at": BASE + timedelta(seconds=15), "kind": "heart_rate"},
        {"recorded_at": BASE + timedelta(seconds=EPOCH_SECONDS), "kind": "heart_rate", "value": 70.0},
    ]
    windows = list(window_readings(readings, epoch_seconds=EPOCH_SECONDS,
                                   context_seconds=CONTEXT_SECONDS))
    assert len(windows) == 2
    assert [r["value"] for r in windows[0]["readings"]] == [60.0]
    # epoch-1's history carries epoch-0's clean hr_mean (60.0), not NaN.
    hist = windows[1]["hr_mean_history"]
    assert hist == [60.0]
    assert not math.isnan(_lag_value(hist, 1))


def test_first_epoch_has_empty_history():
    readings = _flat_stream(n_epochs=3)
    windows = list(window_readings(readings, epoch_seconds=EPOCH_SECONDS,
                                   context_seconds=CONTEXT_SECONDS))
    assert windows[0]["hr_mean_history"] == []
    import math
    assert math.isnan(_lag_value(windows[0]["hr_mean_history"], 1))


# ---- window_readings: tz enforcement + degrade -------------------------------

def test_naive_timestamp_raises_value_error():
    bad = [{"recorded_at": datetime(2026, 5, 29, 3, 0, 0), "kind": "heart_rate", "value": 60.0}]
    with pytest.raises(ValueError):
        list(window_readings(bad, epoch_seconds=EPOCH_SECONDS, context_seconds=CONTEXT_SECONDS))


def test_empty_stream_degrades_to_no_windows():
    assert list(window_readings([], epoch_seconds=EPOCH_SECONDS,
                                context_seconds=CONTEXT_SECONDS)) == []


def test_short_stream_does_not_raise_and_fabricates_nothing():
    readings = _flat_stream(n_epochs=1)
    windows = list(window_readings(readings, epoch_seconds=EPOCH_SECONDS,
                                   context_seconds=CONTEXT_SECONDS))
    assert len(windows) == 1
    assert windows[0]["hr_mean_history"] == []
    # no readings invented beyond what was supplied
    assert all(r in readings for r in windows[0]["readings"])


# ---- synthesize_biometric_window: shape + determinism ------------------------

def test_synthesize_shape():
    w = synthesize_biometric_window(epoch_start_at=BASE, index=0)
    assert set(w) >= {"epoch_start_at", "readings", "hr_mean_history"}
    assert w["epoch_start_at"] == BASE
    assert w["readings"], "synthetic window must carry readings"
    kinds = {r["kind"] for r in w["readings"]}
    assert "heart_rate" in kinds
    for r in w["readings"]:
        assert r["recorded_at"].tzinfo is not None


def test_synthesize_is_deterministic_by_index():
    a = synthesize_biometric_window(epoch_start_at=BASE, index=4)
    b = synthesize_biometric_window(epoch_start_at=BASE, index=4)
    assert a == b


def test_synthesize_varies_by_index():
    a = synthesize_biometric_window(epoch_start_at=BASE, index=0)
    b = synthesize_biometric_window(epoch_start_at=BASE, index=1)
    assert a != b


# ---- END-TO-END SLEEP happy path: L1 -> L2 (24 feats) -> L4 rem (no DB) -------

def _wire_lane(bus: MessageBus) -> tuple[list[MessageEnvelope], list[MessageEnvelope], list[MessageEnvelope]]:
    signals: list[MessageEnvelope] = []
    features: list[MessageEnvelope] = []
    preds: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_SIGNAL, signals.append)
    bus.subscribe(TOPIC_FEATURE, features.append)
    bus.subscribe(TOPIC_PREDICTION, preds.append)
    features_participant.register(bus)       # L2
    prediction_participant.register(bus)     # L4
    return signals, features, preds


def test_sleep_window_flows_to_24_feature_snapshot_and_rem_prediction_no_db():
    bus = MessageBus()
    signals, features, preds = _wire_lane(bus)

    sink = WatchBusSink(bus, meta_context=MetaContext.SLEEP)
    window = synthesize_biometric_window(epoch_start_at=BASE, index=2)
    env = sink.emit_window(
        epoch_start_at=window["epoch_start_at"],
        readings=window["readings"],
        hr_mean_history=window["hr_mean_history"],
    )

    # L1: a biometric SignalPacket on TOPIC_SIGNAL.
    assert signals, "no signal published"
    sig = signals[-1].payload
    assert isinstance(sig, SignalPacket)
    assert sig.modality == Modality.BIOMETRIC.value
    assert sig.intent == Intent.CONTINUOUS.value
    assert sig.kind == KIND_BIOMETRIC_WINDOW
    assert sig.source == WATCH_SOURCE

    # L2: a 24-feature FeatureSnapshot.
    assert features, "no feature snapshot published"
    snap = features[-1].payload
    assert isinstance(snap, FeatureSnapshot)
    assert snap.modality == Modality.BIOMETRIC.value
    assert snap.payload["feature_cols"] == list(FEATURE_COLS)
    assert len(snap.payload["vector"]) == 24
    assert set(snap.payload["features"]) == set(FEATURE_COLS)

    # L4: a "rem" Prediction.
    assert preds, "no prediction published"
    pred = preds[-1].payload
    assert isinstance(pred, Prediction)
    assert pred.axis == "rem"
    assert set(pred.distribution) == {"rem", "non_rem"}
    assert 0.0 <= pred.distribution["rem"] <= 1.0

    # Context / consent / trace propagate L1->L4 (#1 / #11 / #14).
    assert env.meta_context == MetaContext.SLEEP
    assert env.consent_scope == CONSENT_SCOPES["hk"]
    assert features[-1].meta_context == MetaContext.SLEEP
    assert preds[-1].meta_context == MetaContext.SLEEP
    assert preds[-1].consent_scope == CONSENT_SCOPES["hk"]
    trace = signals[-1].trace_id
    assert features[-1].trace_id == trace
    assert preds[-1].trace_id == trace
    # i_model_id propagates when set at L1.
    assert env.i_model_id == preds[-1].i_model_id


def test_emit_window_propagates_i_model_id():
    bus = MessageBus()
    signals, _features, preds = _wire_lane(bus)
    sink = WatchBusSink(bus, meta_context=MetaContext.SLEEP)
    window = synthesize_biometric_window(epoch_start_at=BASE, index=0)
    env = sink.emit_window(
        epoch_start_at=window["epoch_start_at"],
        readings=window["readings"],
        i_model_id="im-123",
    )
    assert env.i_model_id == "im-123"
    assert signals[-1].payload.i_model_id == "im-123"
    assert preds and preds[-1].i_model_id == "im-123"


def test_windowed_real_stream_drives_predictions_end_to_end_no_db():
    # window_readings -> WatchBusSink for every epoch of a multi-epoch stream;
    # each epoch should produce a rem Prediction (the lane is fully wired).
    bus = MessageBus()
    _signals, _features, preds = _wire_lane(bus)
    sink = WatchBusSink(bus, meta_context=MetaContext.SLEEP)
    readings = _flat_stream(n_epochs=6)
    windows = list(window_readings(readings, epoch_seconds=EPOCH_SECONDS,
                                   context_seconds=CONTEXT_SECONDS))
    for w in windows:
        sink.emit_window(
            epoch_start_at=w["epoch_start_at"],
            readings=w["readings"],
            hr_mean_history=w["hr_mean_history"],
        )
    assert len(preds) == len(windows) == 6
    assert all(p.payload.axis == "rem" for p in preds)
