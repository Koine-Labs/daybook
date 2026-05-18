"""MicroPython sensor mock for Daybook ESP32.

Flash to ESP32 connected to Pi via USB. Emits JSON-line sensor packets over UART
per apps/AI_PI_CONTRACT.md so the full Daybook pipeline can run on synthetic
data before the BioAmp EXG Pill arrives.

Cadence + values are chosen to look like a calm, sleeping human:
  - heart_rate: every 4s, drifts in 50-80 bpm range (light bumps in REM windows)
  - hrv (SDNN): every 60s, drifts in 25-55 ms range
  - respiratory_rate: every 30s, drifts in 11-16 breaths/min range
  - spo2: every 60s, drifts in 95-99 range

REM windows are simulated at ~95, 240, 380, 510 minutes from start (matching
apps/pi/sensors/mock.py's typical cycle layout). During a REM window, heart
rate and respiratory rate drift upward; HRV drifts downward slightly.

Output format is one newline-delimited JSON object per packet on stdout,
which is UART when flashed (the Pi-side esp32_serial source readline()s these).
"""

try:
    import urandom as _random
except ImportError:
    import random as _random

try:
    from time import ticks_ms, ticks_diff, sleep_ms
    _HOST_CPYTHON = False
except ImportError:
    import time as _time

    def ticks_ms():
        return int(_time.monotonic() * 1000)

    def ticks_diff(a, b):
        return a - b

    def sleep_ms(ms):
        _time.sleep(ms / 1000.0)

    _HOST_CPYTHON = True

import json


HR_INTERVAL_MS = 4_000
HRV_INTERVAL_MS = 60_000
RESP_INTERVAL_MS = 30_000
SPO2_INTERVAL_MS = 60_000

LOOP_TICK_MS = 200

REM_WINDOWS_MINUTES = (95, 240, 380, 510)
REM_DURATION_MINUTES = 20

HR_CENTER = 62.0
HR_MIN, HR_MAX = 50.0, 80.0
HR_REM_BUMP = 8.0

HRV_CENTER = 38.0
HRV_MIN, HRV_MAX = 25.0, 55.0
HRV_REM_DROP = 5.0

RESP_CENTER = 13.0
RESP_MIN, RESP_MAX = 11.0, 16.0
RESP_REM_BUMP = 1.5

SPO2_CENTER = 97.5
SPO2_MIN, SPO2_MAX = 95.0, 99.0

SOURCE_ID = "esp32_mock"


def _gauss(spread):
    """Cheap pseudo-gaussian via sum-of-uniforms (MicroPython has no random.gauss)."""
    s = 0.0
    for _ in range(4):
        s += _random.random()
    return (s - 2.0) * spread


def _clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _walk(value, center, lo, hi, drift, mean_reversion=0.05):
    """One step of a bounded random walk that gently returns to center."""
    pull = (center - value) * mean_reversion
    return _clamp(value + pull + _gauss(drift), lo, hi)


def _iso_now():
    """Best-effort ISO 8601 UTC string with millis.

    Real ESP32s often lack a real-time clock until NTP-sync over WiFi. If the
    Pi receives a missing/unparseable recorded_at, the esp32_serial source
    stamps with Pi clock instead.
    """
    if _HOST_CPYTHON:
        import time as _time
        now_s = _time.time()
        secs = int(now_s)
        ms = int((now_s - secs) * 1000)
        try:
            return _time.strftime("%Y-%m-%dT%H:%M:%S", _time.gmtime(secs)) + ".{:03d}Z".format(ms)
        except Exception:
            return None
    try:
        import utime
        now_s = utime.time()
        tt = utime.gmtime(now_s)
        return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}.000Z".format(
            tt[0], tt[1], tt[2], tt[3], tt[4], tt[5]
        )
    except Exception:
        return None


def _in_rem(elapsed_minutes):
    for start in REM_WINDOWS_MINUTES:
        if start <= elapsed_minutes < start + REM_DURATION_MINUTES:
            return True
    return False


def _payload(kind, value):
    if kind == "heart_rate":
        return {"bpm": round(value, 1), "unit": "count/min"}
    if kind == "hrv":
        return {"rmssdMs": round(value, 1), "unit": "ms"}
    if kind == "respiratory_rate":
        return {"breathsPerMinute": round(value, 1), "unit": "count/min"}
    if kind == "spo2":
        return {"percent": round(value, 1), "unit": "%"}
    return {"value": value}


def emit(kind, value, recorded_at_iso):
    packet = {
        "kind": kind,
        "value": round(value, 2),
        "source": SOURCE_ID,
        "payload": _payload(kind, value),
    }
    if recorded_at_iso is not None:
        packet["recorded_at"] = recorded_at_iso
    print(json.dumps(packet))


def run(seconds_limit=None):
    """Main loop. seconds_limit is for local dev testing; None = forever."""
    start = ticks_ms()
    next_hr = ticks_ms()
    next_hrv = ticks_ms() + 5_000
    next_resp = ticks_ms() + 10_000
    next_spo2 = ticks_ms() + 15_000

    hr = HR_CENTER
    hrv = HRV_CENTER
    resp = RESP_CENTER
    spo2 = SPO2_CENTER

    while True:
        now = ticks_ms()
        elapsed_ms = ticks_diff(now, start)
        if seconds_limit is not None and elapsed_ms >= seconds_limit * 1000:
            return

        elapsed_minutes = elapsed_ms / 60_000.0
        rem = _in_rem(elapsed_minutes)
        recorded_at_iso = _iso_now()

        if ticks_diff(now, next_hr) >= 0:
            hr_center_now = HR_CENTER + (HR_REM_BUMP if rem else 0.0)
            hr = _walk(hr, hr_center_now, HR_MIN, HR_MAX, drift=1.2)
            emit("heart_rate", hr, recorded_at_iso)
            next_hr = now + HR_INTERVAL_MS

        if ticks_diff(now, next_hrv) >= 0:
            hrv_center_now = HRV_CENTER - (HRV_REM_DROP if rem else 0.0)
            hrv = _walk(hrv, hrv_center_now, HRV_MIN, HRV_MAX, drift=2.5)
            emit("hrv", hrv, recorded_at_iso)
            next_hrv = now + HRV_INTERVAL_MS

        if ticks_diff(now, next_resp) >= 0:
            resp_center_now = RESP_CENTER + (RESP_REM_BUMP if rem else 0.0)
            resp = _walk(resp, resp_center_now, RESP_MIN, RESP_MAX, drift=0.4)
            emit("respiratory_rate", resp, recorded_at_iso)
            next_resp = now + RESP_INTERVAL_MS

        if ticks_diff(now, next_spo2) >= 0:
            spo2 = _walk(spo2, SPO2_CENTER, SPO2_MIN, SPO2_MAX, drift=0.3)
            emit("spo2", spo2, recorded_at_iso)
            next_spo2 = now + SPO2_INTERVAL_MS

        sleep_ms(LOOP_TICK_MS)


if __name__ == "__main__":
    import sys

    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            limit = None
    run(seconds_limit=limit)
