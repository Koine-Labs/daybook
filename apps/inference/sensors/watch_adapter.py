"""L1 biometric producer: windowed watch HR/HRV/resp/SpO2 -> SignalPacket on the bus.

Mirrors sensors/audio_adapter.py. Transport-agnostic: holds only a MessageBus,
so the SAME class works over InProcessTransport (DB-replay on the Mac today) and
NetworkTransport (watch-as-satellite later) with no change. Semantic-first (#11):
only already-derived per-30s biometric readings ride the bus, never raw waveform.

`window_readings` is the pure windower that turns a time-ordered flat reading
stream into the successive epoch-window payloads features/biometric.py expects —
each carrying its preceding context window of readings and the oldest-first
`hr_mean_history` of prior-epoch hr_means (consumed by features/biometric.py.
_lag_value as history[-k]). `synthesize_biometric_window` is the deterministic
CI/demo generator (no DB), varying by an integer index, never random.

The epoch/context windowing constants are imported from features.biometric — the
single source of truth — and never redefined here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Sequence

from core.bus.bus import MessageBus
from core.protocol.enums import Intent, MetaContext, Modality
from core.protocol.envelope import MessageEnvelope
from features.biometric import CONTEXT_SECONDS, EPOCH_SECONDS
from sensors.contract import DEFAULT_USER_ID, IntentTaggedReading
from sensors.participant import emit

KIND_BIOMETRIC_WINDOW = "biometric_window"
WATCH_SOURCE = "watch.biometric_window"  # matches features/biometric.py.SOURCE

_BIOMETRIC_KINDS = ("heart_rate", "hrv", "respiratory_rate", "spo2")


def _to_utc(value: Any) -> datetime:
    """Coerce a datetime/ISO string into tz-aware UTC; reject naive timestamps."""
    ts = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if ts.tzinfo is None:
        raise ValueError("biometric reading timestamps must be tz-aware UTC")
    return ts.astimezone(timezone.utc)


def _hr_mean(readings: Sequence[dict[str, Any]], lo: datetime, hi: datetime) -> float:
    """Mean heart_rate in [lo, hi), or NaN when the window has none.

    Mirrors classifier.features.compute_session_features: an empty HR window
    yields NaN (not a skip), so every epoch contributes one positionally-aligned
    hr_mean_history entry. NaN values are already dropped at normalization, so
    they never poison the mean.
    """
    vals = [r["value"] for r in readings
            if r["kind"] == "heart_rate" and lo <= r["recorded_at"] < hi]
    if not vals:
        return float("nan")
    return sum(vals) / len(vals)


def window_readings(
    readings: Sequence[dict[str, Any]],
    *,
    epoch_seconds: int = EPOCH_SECONDS,
    context_seconds: int = CONTEXT_SECONDS,
) -> Iterator[dict[str, Any]]:
    """Time-ordered flat readings -> successive epoch-window payloads (pure).

    Each yielded payload is the features/biometric.py shape:
    {epoch_start_at, readings (the [epoch-context, epoch+epoch) slice),
    hr_mean_history (oldest-first prior-epoch hr_means)}. Empty/short input
    degrades to zero/one window without fabricating any values, and never raises
    on a well-formed short stream. Naive timestamps raise ValueError.
    """
    normalized: list[dict[str, Any]] = []
    for r in readings:
        if r.get("kind") not in _BIOMETRIC_KINDS:
            continue
        try:
            val = float(r["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if val != val:  # NaN — dropped before averaging, mirroring _parse_window
            continue
        normalized.append({"recorded_at": _to_utc(r["recorded_at"]), "kind": r["kind"], "value": val})
    if not normalized:
        return
    normalized.sort(key=lambda r: r["recorded_at"])

    step = timedelta(seconds=epoch_seconds)
    context = timedelta(seconds=context_seconds)
    first = normalized[0]["recorded_at"]
    last = normalized[-1]["recorded_at"]

    epoch_start = first
    hr_mean_history: list[float] = []
    while epoch_start <= last:
        lo = epoch_start - context
        hi = epoch_start + step
        window = [r for r in normalized if lo <= r["recorded_at"] < hi]
        yield {
            "epoch_start_at": epoch_start,
            "readings": window,
            "hr_mean_history": list(hr_mean_history),
        }
        # Always advance one entry per epoch (NaN for an empty HR window), so
        # _lag_value(history, k) == compute_session_features' positional lag.
        hr_mean_history.append(_hr_mean(normalized, lo, hi))
        epoch_start = epoch_start + step


def synthesize_biometric_window(
    *,
    epoch_start_at: datetime,
    index: int = 0,
    hr_per_epoch: int = 6,
    context_seconds: int = CONTEXT_SECONDS,
    epoch_seconds: int = EPOCH_SECONDS,
) -> dict[str, Any]:
    """Deterministic synthetic epoch window (no DB) for CI + demo.

    Mirrors bci.eeg_adapter.synthesize_eeg_window: varies by an integer `index`,
    never random. Fills the [epoch_start-context, epoch_start+epoch) span with
    heart_rate / hrv / respiratory_rate / spo2 readings so the produced window is
    a complete 24-feature epoch, plus a deterministic prior-epoch hr_mean_history.
    """
    if epoch_start_at.tzinfo is None:
        raise ValueError("epoch_start_at must be tz-aware UTC")
    epoch_start_at = epoch_start_at.astimezone(timezone.utc)

    hr_base = 56.0 + (index % 12)
    span_start = epoch_start_at - timedelta(seconds=context_seconds)
    span_end = epoch_start_at + timedelta(seconds=epoch_seconds)
    n_slots = int((span_end - span_start).total_seconds() // 5)

    readings: list[dict[str, Any]] = []
    for slot in range(n_slots):
        t = span_start + timedelta(seconds=5 * slot)
        phase = (index + slot) % 8
        readings.append({"recorded_at": t, "kind": "heart_rate", "value": hr_base + phase})
        if slot % 2 == 0:
            readings.append({"recorded_at": t, "kind": "hrv", "value": 38.0 + (index % 5) + (slot % 4)})
        if slot % 3 == 0:
            readings.append({"recorded_at": t, "kind": "respiratory_rate", "value": 13.0 + (index % 3)})
        if slot % 4 == 0:
            readings.append({"recorded_at": t, "kind": "spo2", "value": 96.0 + (index % 3)})

    n_history = min(5, index)
    hr_mean_history = [float(hr_base - n_history + k) for k in range(n_history)]

    return {
        "epoch_start_at": epoch_start_at,
        "readings": readings,
        "session_started_at": span_start,
        "hr_mean_history": hr_mean_history,
    }


class WatchBusSink:
    """Emits windowed biometric SignalPackets onto a MessageBus (no raw waveform).

    `meta_context` is the top-level context (#14) the emitted signals ride under;
    it defaults to UNKNOWN so callers/tests are unchanged. The replay runner passes
    SLEEP so L4's REM nowcaster — a sleep-only model — scores in a sleep frame.
    """

    def __init__(
        self,
        bus: MessageBus,
        *,
        user_id: str = DEFAULT_USER_ID,
        meta_context: MetaContext = MetaContext.UNKNOWN,
    ) -> None:
        self.bus = bus
        self.user_id = user_id
        self.meta_context = meta_context

    def emit_window(
        self,
        *,
        epoch_start_at: datetime,
        readings: Sequence[dict[str, Any]],
        session_started_at: datetime | None = None,
        hr_mean_history: Sequence[float] | None = None,
        user_id: str | None = None,
        i_model_id: str | None = None,
    ) -> MessageEnvelope:
        """Build the features/biometric.py payload and emit it as a SignalPacket.

        Datetimes are serialized to ISO-8601 strings at this seam — the canonical
        wire shape features/biometric.py documents — so the payload JSON-encodes
        on NetworkTransport exactly as it rides InProcessTransport.
        """
        payload: dict[str, Any] = {
            "epoch_start_at": _to_utc(epoch_start_at).isoformat(),
            "readings": [
                {**r, "recorded_at": _to_utc(r["recorded_at"]).isoformat()}
                for r in readings
            ],
        }
        if session_started_at is not None:
            payload["session_started_at"] = _to_utc(session_started_at).isoformat()
        if hr_mean_history is not None:
            payload["hr_mean_history"] = [float(v) for v in hr_mean_history]
        reading = IntentTaggedReading(
            modality=Modality.BIOMETRIC.value,
            intent=Intent.CONTINUOUS.value,
            kind=KIND_BIOMETRIC_WINDOW,
            payload=payload,
            source=WATCH_SOURCE,
            timestamp=_to_utc(epoch_start_at),
            user_id=user_id or self.user_id,
            i_model_id=i_model_id,
        )
        return emit(self.bus, reading, meta_context=self.meta_context)
