"""Band-power extraction — Welch PSD of a 1-D EEG window -> band powers.

Pure numpy/scipy. The edge (Pi/ESP32) computes band-powers from raw ADC windows
and DISCARDS the raw EEG; only the resulting semantic band-power dict rides the
bus (semantic-first, #11). This module is the single reusable canonical math the
firmware stub and the synthetic test harness both call — the BCI lane's analog of
classifier/features.py for biometric.

No DB, no bus, no I/O. Importable with no DATABASE_URL.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from scipy.signal import welch

# Standard clinical EEG bands (Hz). 45 Hz upper bound keeps clear of 50/60 Hz
# mains; a notch is a firmware concern (see bci/firmware/eeg_edge_stub.py).
BANDS: dict[str, tuple[float, float]] = {
    "delta": (0.5, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
    "gamma": (30.0, 45.0),
}
DEFAULT_FS = 256.0
VERSION = "bandpower.v1"

# Analysis band over which relative powers are normalized (delta_lo .. gamma_hi).
_ANALYSIS_LO = BANDS["delta"][0]
_ANALYSIS_HI = BANDS["gamma"][1]

# In-band total-power floor: below this the spectrum is only numerical leakage from
# out-of-band content, so we degrade to a zero result instead of fabricating a
# dominant band. Far below any real EEG window's in-band power.
_MIN_TOTAL_POWER = 1e-12


def _zero_result(fs: float, n: int) -> dict[str, Any]:
    """Honest degraded result: bands present at 0.0, no dominant band, no crash."""
    return {
        "absolute": {b: 0.0 for b in BANDS},
        "relative": {b: 0.0 for b in BANDS},
        "total_power": 0.0,
        "dominant_band": None,
        "fs": fs,
        "n_samples": n,
        "method": "welch",
        "version": VERSION,
    }


def compute_band_powers(samples: Sequence[float], *, fs: float = DEFAULT_FS) -> dict[str, Any]:
    """Welch PSD of a 1-D EEG window -> absolute + relative band powers.

    Returns a dict with absolute (V^2) and relative (sum ~= 1.0) power per band,
    total_power over the analysis band, the dominant band (argmax of absolute),
    and provenance metadata. All-zero or too-short input degrades to a zero
    result (never fabricates); NaN/inf samples raise ValueError (bad input is a
    bug, not a degraded state).
    """
    x = np.asarray(samples, dtype=float).ravel()
    n = int(x.size)
    if n and not np.all(np.isfinite(x)):
        raise ValueError("EEG samples must be finite (no NaN/inf)")

    # Too short to compute a meaningful PSD, or empty -> honest zero result.
    # Floor = one full cycle of the lowest analysis frequency (fs/_ANALYSIS_LO samples).
    # NOTE: nperseg is capped at fs (1.0s segments) below, so frequency resolution is
    # fixed at df = fs/nperseg = 1.0 Hz regardless of window length — the lowest non-DC
    # bin is 1.0 Hz, so delta's 0.5 Hz low edge is NOT separately resolved (it folds
    # into the 1.0 Hz bin). Longer windows reduce Welch variance, not df. True 0.5 Hz
    # resolution would require nperseg >= 2*fs (and a window at least that long); not
    # needed for dominant-band detection, which is all this lane consumes.
    min_samples = int(np.ceil(fs / _ANALYSIS_LO))
    if n < min_samples:
        return _zero_result(fs, n)
    if not np.any(x):
        return _zero_result(fs, n)

    nperseg = int(min(n, fs))
    freqs, psd = welch(x, fs=fs, nperseg=nperseg, scaling="density")

    absolute: dict[str, float] = {}
    for band, (lo, hi) in BANDS.items():
        mask = (freqs >= lo) & (freqs < hi)
        if not np.any(mask):
            absolute[band] = 0.0
            continue
        power = float(np.trapezoid(psd[mask], freqs[mask]))
        absolute[band] = max(0.0, power)

    # Absolute floor (not just <= 0): a signal entirely outside the 0.5-45 Hz analysis
    # band (e.g. a 47 Hz tone) leaks only numerical-noise power into the bands. Below
    # this floor there is no real in-band energy, so degrade honestly rather than
    # reporting a leakage-driven dominant band.
    total = float(sum(absolute.values()))
    if total <= _MIN_TOTAL_POWER:
        return _zero_result(fs, n)

    relative = {b: absolute[b] / total for b in BANDS}
    dominant = max(BANDS, key=lambda b: absolute[b])

    return {
        "absolute": absolute,
        "relative": relative,
        "total_power": total,
        "dominant_band": dominant,
        "fs": fs,
        "n_samples": n,
        "method": "welch",
        "version": VERSION,
    }
