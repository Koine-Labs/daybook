"""Off-CI reference: the ADC -> band-power -> emit edge loop for the EXG Pill.

This is the documented edge contract, ready for the BioAmp EXG Pill (single-channel
biopotential amp). It runs TODAY on a laptop with NO hardware (synthetic generator
+ InProcessTransport); on the real rig the only swaps are (1) point `read_window`
at the real ADC and (2) bind the sink to a NetworkTransport-backed bus.

It is NOT collected by CI: bci/ is a collected dir, but bci/firmware/ carries no
test_*.py so nothing is collected here. It imports the real
bci.bandpower.compute_band_powers + sensors.eeg_adapter.EEGBusSink so the edge and
the lane share one semantic contract.

Run locally (synthetic, no hardware, no DB; uses InProcessTransport):
    cd apps/inference && python -m bci.firmware.eeg_edge_stub --windows 5

──────────────────────────────────────────────────────────────────────────────
SEMANTIC-FIRST EDGE LOOP (#11) — raw EEG is computed-then-discarded on-device:

    loop @ window cadence (e.g. every 1.0s, 2.0s window, 50% overlap):
        raw = adc.read_window(fs=256, seconds=2.0)        # EXG Pill -> ADC -> buffer
        raw = notch_50_60(raw); raw = bandpass_0p5_45(raw)# mains + out-of-band (firmware DSP)
        bp  = compute_band_powers(raw, fs=256)            # SEMANTIC extraction at the edge
        del raw                                           # RAW DISCARDED — never leaves device
        sink.emit_band_powers(user_id=UID, recorded_at=now_utc(), band_powers=bp)

──────────────────────────────────────────────────────────────────────────────
AI_PI_CONTRACT alignment (additive minor-version note for the Pi chat to append):

  - AI_PI_CONTRACT.md reserves EEG via per-band-microvolt kinds
    (`eeg_alpha`/`eeg_beta`/`eeg_theta`, payload `{"microvolts": ..., "unit": "uV"}`)
    and says EEG bands are FUTURE — "emit them now if available, but the v0
    classifier ignores them." This BCI lane is the consumer that stops ignoring them.
  - The per-band-microvolt rows are the raw-ish LEGACY shape. The nervous-system
    bus instead carries ONE consolidated `eeg_bandpower` semantic packet (all five
    bands' absolute+relative power + derived) per window — strictly more semantic-
    first (#11) than five separate microvolt rows, and it matches
    SignalPacket(modality=BCI, kind="eeg_bandpower") the lane consumes.
  - The contract's `source` maps to EEGBusSink.EEG_SOURCE: the real Pi sets
    source="esp32_bioamp_pill" (vs the stub's "eeg_edge_v1").
  - This is an ADDITIVE minor-version note (no breaking change; the legacy per-band
    kinds remain documented), to append to AI_PI_CONTRACT.md when the Pi wires the
    producer.

OPEN HARDWARE QUESTIONS (inherited from the contract — for the hardware chat, the
AI side stays agnostic exactly as the contract states):
  - sampling rate vs the EXG Pill's analog bandwidth (256 Hz assumed here)
  - notch frequency: 50 Hz vs 60 Hz mains (region-dependent)
  - transport: serial (USB) vs WiFi from ESP32 -> Pi hub

CALIBRATION-ON-ARRIVAL (why this is "plug-and-play, a calibration task"):
  When the EXG Pill arrives: (1) point read_window at the real device; (2) record
  a few labeled waking windows (idle vs focused) to FIT
  fusion.axes.cognitive_load._ENGAGE_LO/_ENGAGE_HI (today's documented placeholders)
  — replacing those two constants is the ONLY numerical calibration step; the entire
  L1->L2->L3 plumbing, contracts, and tests are already in place and green.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Callable, Sequence

import numpy as np

from bci.bandpower import DEFAULT_FS, compute_band_powers
from core.bus.bus import TOPIC_SIGNAL, MessageBus
from core.protocol.enums import MetaContext
from sensors.contract import DEFAULT_USER_ID
from sensors.eeg_adapter import EEGBusSink, synthesize_eeg_window

# On the real rig this reads the EXG Pill ADC; here it is the synthetic generator.
RawReader = Callable[[], Sequence[float]]


def notch_50_60(raw: np.ndarray) -> np.ndarray:
    """Firmware DSP placeholder: mains-frequency notch (50/60 Hz). No-op in the stub."""
    return raw


def bandpass_0p5_45(raw: np.ndarray) -> np.ndarray:
    """Firmware DSP placeholder: 0.5-45 Hz band-pass. No-op in the stub."""
    return raw


def _synthetic_reader(*, fs: float, seconds: float, seed: int) -> RawReader:
    counter = {"i": 0}

    def read() -> np.ndarray:
        counter["i"] += 1
        # Alternate focused/relaxed windows so the demo shows load varying.
        mix = {"beta": 25.0} if counter["i"] % 2 else {"alpha": 25.0}
        return synthesize_eeg_window(fs=fs, seconds=seconds, band_mix=mix,
                                     noise_uv=2.0, seed=seed + counter["i"])

    return read


def run_edge_loop(
    sink: EEGBusSink,
    *,
    read_window: RawReader,
    windows: int,
    fs: float = DEFAULT_FS,
    user_id: str = DEFAULT_USER_ID,
) -> int:
    """The semantic-first edge loop: read raw, extract band powers, DISCARD raw, emit.

    Returns the number of semantic packets emitted. On the real rig, swap
    `read_window` for the ADC reader and the sink's bus for a NetworkTransport bus.
    """
    emitted = 0
    for _ in range(windows):
        raw = np.asarray(read_window(), dtype=float)
        raw = bandpass_0p5_45(notch_50_60(raw))  # firmware DSP (no-op in stub)
        bp = compute_band_powers(raw, fs=fs)      # semantic extraction at the edge
        del raw                                   # RAW DISCARDED — never leaves the device
        sink.emit_band_powers(
            user_id=user_id, recorded_at=datetime.now(timezone.utc), band_powers=bp
        )
        emitted += 1
    return emitted


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic EEG edge stub (no hardware, no DB).")
    parser.add_argument("--windows", type=int, default=5)
    parser.add_argument("--fs", type=float, default=DEFAULT_FS)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    bus = MessageBus()  # InProcessTransport; real rig binds NetworkTransport.
    seen: list = []
    bus.subscribe(TOPIC_SIGNAL, seen.append)
    sink = EEGBusSink(bus, fs=args.fs, meta_context=MetaContext.WAKING)

    reader = _synthetic_reader(fs=args.fs, seconds=args.seconds, seed=args.seed)
    emitted = run_edge_loop(sink, read_window=reader, windows=args.windows, fs=args.fs)

    print(f"emitted {emitted} eeg_bandpower packets (raw discarded at the edge)")
    for env in seen:
        p = env.payload.payload
        assert "samples" not in p  # invariant: no raw on the bus
        print(f"  dominant={p['dominant_band']:>5}  total_power={p['total_power']:.4f}")


if __name__ == "__main__":
    main()
