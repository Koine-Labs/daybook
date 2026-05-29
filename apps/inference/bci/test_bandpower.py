"""Band-power on known synthetic signals — no bus, no DB, no network.

Validates compute_band_powers against sinusoids whose dominant band is known a
priori, plus scale-invariance, two-tone mixing, white noise, and degraded inputs.
Assertions are on RELATIVE power (scale-invariant) per the spec.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from bci.bandpower import BANDS, DEFAULT_FS, compute_band_powers


def _sinusoid(freq: float, *, fs: float = DEFAULT_FS, seconds: float = 2.0,
              amplitude: float = 1.0) -> np.ndarray:
    t = np.arange(int(round(fs * seconds))) / fs
    return amplitude * np.sin(2.0 * math.pi * freq * t)


def test_10hz_sinusoid_alpha_dominant():
    bp = compute_band_powers(_sinusoid(10.0))
    assert bp["dominant_band"] == "alpha"
    rel = bp["relative"]
    assert rel["alpha"] > 0.5
    assert all(rel["alpha"] > rel[b] for b in BANDS if b != "alpha")


def test_6hz_sinusoid_theta_dominant():
    bp = compute_band_powers(_sinusoid(6.0))
    assert bp["dominant_band"] == "theta"


@pytest.mark.parametrize("freq,band", [
    (2.0, "delta"),
    (6.0, "theta"),
    (10.0, "alpha"),
    (22.0, "beta"),
    (40.0, "gamma"),
])
def test_single_tone_lands_in_expected_band(freq, band):
    bp = compute_band_powers(_sinusoid(freq))
    assert bp["dominant_band"] == band
    assert bp["relative"][band] > 0.5


@pytest.mark.parametrize("freq", [2.0, 6.0, 10.0, 22.0, 40.0])
def test_relatives_sum_to_one(freq):
    bp = compute_band_powers(_sinusoid(freq))
    assert abs(sum(bp["relative"].values()) - 1.0) < 1e-6


def test_two_tone_elevates_two_bands():
    sig = _sinusoid(10.0) + _sinusoid(22.0)
    bp = compute_band_powers(sig)
    rel = bp["relative"]
    assert rel["alpha"] > rel["delta"]
    assert rel["beta"] > rel["delta"]
    assert rel["alpha"] + rel["beta"] > 0.5


def test_amplitude_scaling_invariance():
    base = compute_band_powers(_sinusoid(10.0, amplitude=1.0))
    scaled = compute_band_powers(_sinusoid(10.0, amplitude=5.0))
    for band in BANDS:
        assert abs(base["relative"][band] - scaled["relative"][band]) < 1e-6
    # Absolute total power scales ~ amplitude^2 (= 25x).
    ratio = scaled["total_power"] / base["total_power"]
    assert abs(ratio - 25.0) / 25.0 < 0.05


def test_all_zeros_degrades_to_zero_no_crash():
    bp = compute_band_powers(np.zeros(int(DEFAULT_FS * 2)))
    assert bp["total_power"] == 0.0
    assert bp["dominant_band"] is None
    assert all(bp["absolute"][b] == 0.0 for b in BANDS)
    assert all(bp["relative"][b] == 0.0 for b in BANDS)


def test_too_short_window_degrades_no_crash():
    bp = compute_band_powers([0.1, 0.2, 0.3, 0.4, 0.5])
    assert bp["total_power"] == 0.0
    assert bp["dominant_band"] is None


def test_nan_input_rejected():
    bad = _sinusoid(10.0)
    bad[3] = float("nan")
    with pytest.raises(ValueError):
        compute_band_powers(bad)


def test_inf_input_rejected():
    bad = _sinusoid(10.0)
    bad[3] = float("inf")
    with pytest.raises(ValueError):
        compute_band_powers(bad)


def test_above_band_only_tone_degrades_no_leakage_dominant():
    # A 47 Hz tone is above the 0.5-45 Hz analysis band but below Nyquist (128 Hz):
    # only numerical leakage reaches the bands, so it must degrade to an honest zero
    # result rather than reporting a leakage-driven dominant band.
    bp = compute_band_powers(_sinusoid(47.0))
    assert bp["dominant_band"] is None
    assert bp["total_power"] == 0.0


def test_white_noise_no_single_band_majority():
    rng = np.random.default_rng(0)
    noise = rng.standard_normal(int(DEFAULT_FS * 4))
    bp = compute_band_powers(noise)
    assert max(bp["relative"].values()) < 0.6


def test_metadata_fields_present():
    bp = compute_band_powers(_sinusoid(10.0))
    assert bp["fs"] == DEFAULT_FS
    assert bp["n_samples"] == int(DEFAULT_FS * 2)
    assert bp["method"] == "welch"
    assert bp["version"] == "bandpower.v1"
