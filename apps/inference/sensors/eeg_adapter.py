"""L1 EEG producer: semantic band-power packets -> SignalPacket on the bus.

Mirrors sensors/audio_adapter.py. Transport-agnostic: holds only a MessageBus,
so the SAME class works over InProcessTransport (synthetic on the Mac today) and
NetworkTransport (Pi later) with no change. Semantic-first (#11): the edge
computes band-powers from a raw ADC window and DISCARDS the raw — only the
semantic band-power dict ever becomes a payload. Raw EEG never rides the bus.

`synthesize_eeg_window` is the only place a raw waveform exists in tests / local
running; it is consumed by compute_band_powers and discarded, mirroring the edge
discard rule.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Sequence

import numpy as np

from bci.bandpower import BANDS, DEFAULT_FS, compute_band_powers
from core.bus.bus import MessageBus
from core.protocol.enums import Intent, MetaContext, Modality
from sensors.contract import DEFAULT_USER_ID, IntentTaggedReading
from sensors.participant import emit

# Band-center frequencies used by the synthetic generator (midpoints of BANDS).
_BAND_CENTERS: dict[str, float] = {b: 0.5 * (lo + hi) for b, (lo, hi) in BANDS.items()}
_DEFAULT_BAND_MIX: dict[str, float] = {"alpha": 20.0}  # relaxed-waking, alpha-dominant


def synthesize_eeg_window(
    *,
    fs: float = DEFAULT_FS,
    seconds: float = 2.0,
    band_mix: dict[str, float] | None = None,
    noise_uv: float = 2.0,
    seed: int | None = None,
) -> np.ndarray:
    """Sum of band-center sinusoids + Gaussian noise -> a 1-D raw EEG window (uV).

    `band_mix` maps band name -> amplitude (uV); default is alpha-dominant. Select
    a theta-/beta-heavy mix to drive the cognitive_load heuristic in either
    direction. This raw waveform exists only here and in tests — it is never a
    payload (#11).
    """
    mix = band_mix if band_mix is not None else _DEFAULT_BAND_MIX
    n = int(round(fs * seconds))
    t = np.arange(n) / fs
    signal = np.zeros(n, dtype=float)
    for band, amp in mix.items():
        freq = _BAND_CENTERS.get(band)
        if freq is None:
            raise ValueError(f"unknown band {band!r}; expected one of {sorted(_BAND_CENTERS)}")
        signal += amp * np.sin(2.0 * math.pi * freq * t)
    if noise_uv > 0.0:
        rng = np.random.default_rng(seed)
        signal += rng.normal(0.0, noise_uv, size=n)
    return signal


class EEGBusSink:
    """Emits eeg_bandpower SignalPackets onto a MessageBus. Raw EEG never rides the bus.

    `meta_context` is the top-level context (#14) the emitted signals ride under;
    it defaults to UNKNOWN so callers/tests are unchanged. The waking runner passes
    WAKING so cognitive_load (a WAKING sub-context signal) lands in a waking frame.
    """

    KIND = "eeg_bandpower"
    EEG_SOURCE = "eeg_edge_v1"  # real Pi sets source='esp32_bioamp_pill' per AI_PI_CONTRACT

    def __init__(
        self,
        bus: MessageBus,
        *,
        user_id: str = DEFAULT_USER_ID,
        fs: float = DEFAULT_FS,
        meta_context: MetaContext = MetaContext.UNKNOWN,
    ) -> None:
        self.bus = bus
        self.user_id = user_id
        self.fs = fs
        self.meta_context = meta_context

    def _payload(self, bp: dict[str, Any]) -> dict[str, Any]:
        """Semantic-first payload — band powers + derived only, NO samples."""
        return {
            "absolute": bp["absolute"],
            "relative": bp["relative"],
            "total_power": bp["total_power"],
            "dominant_band": bp["dominant_band"],
            "fs": bp["fs"],
            "n_samples": bp["n_samples"],
            "channel": "single",
            "method": bp.get("method", "welch"),
            "bandpower_version": bp.get("version", "bandpower.v1"),
        }

    def _emit(self, *, user_id: str, recorded_at: datetime, payload: dict[str, Any]) -> None:
        reading = IntentTaggedReading(
            modality=Modality.BCI.value,
            intent=Intent.CONTINUOUS.value,
            kind=self.KIND,
            payload=payload,
            source=self.EEG_SOURCE,
            timestamp=recorded_at,
            user_id=user_id,
        )
        emit(self.bus, reading, meta_context=self.meta_context)

    def write_window(self, *, user_id: str, recorded_at: datetime, samples: Sequence[float]) -> None:
        """Compute band powers from a raw window, discard the raw, emit a semantic packet."""
        bp = compute_band_powers(samples, fs=self.fs)
        self._emit(user_id=user_id, recorded_at=recorded_at, payload=self._payload(bp))

    def emit_band_powers(self, *, user_id: str, recorded_at: datetime, band_powers: dict[str, Any]) -> None:
        """Edge variant: the Pi already computed band powers; emit them directly (no raw)."""
        self._emit(user_id=user_id, recorded_at=recorded_at, payload=self._payload(band_powers))
