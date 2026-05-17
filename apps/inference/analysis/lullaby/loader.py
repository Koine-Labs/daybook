"""
Data loading and mock session generation for Lullaby sleep analysis.

Handles:
- Parsing exported JSON from the Lullaby iOS app
- Flattening nested watch packets into per-sensor DataFrames
- Generating physiologically plausible synthetic sleep sessions for testing
"""

from __future__ import annotations

import json
import uuid
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Core data container
# ---------------------------------------------------------------------------

@dataclass
class SleepSessionData:
    """Parsed sleep session with sensor data in DataFrames."""

    session_id: str
    start_time: datetime
    end_time: Optional[datetime]
    duration_hours: float

    # Per-sensor DataFrames (timestamps are seconds since session start)
    heart_rate: pd.DataFrame      # columns: timestamp, bpm
    hrv: pd.DataFrame             # columns: timestamp, sdnn
    accelerometer: pd.DataFrame   # columns: timestamp, x, y, z
    sonar: pd.DataFrame           # columns: timestamp, breathing_rate, breathing_regularity, signal_strength
    audio: pd.DataFrame           # columns: timestamp, dominant_frequency, spectral_centroid, rms_energy, zcr, classification
    sleep_stages: pd.DataFrame    # columns: start, end, stage

    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# JSON loading
# ---------------------------------------------------------------------------

def load_session(path: str | Path) -> SleepSessionData:
    """Load a single Lullaby session JSON file.

    The JSON schema matches the Swift `SleepSession` struct exported by
    `JSONExporter.swift` with `.iso8601` date encoding and `.sortedKeys`.

    Args:
        path: Path to the JSON file.

    Returns:
        A SleepSessionData with all sensor streams as DataFrames.
    """
    path = Path(path)
    with open(path, "r") as f:
        raw = json.load(f)

    # Parse dates
    start_time = _parse_iso8601(raw["startDate"])
    end_time = _parse_iso8601(raw.get("endDate")) if raw.get("endDate") else None
    if end_time:
        duration_hours = (end_time - start_time).total_seconds() / 3600
    else:
        duration_hours = 0.0

    # Flatten watch packets into per-sensor lists
    hr_rows = []
    hrv_rows = []
    accel_rows = []

    for packet in raw.get("watchPackets", []):
        for s in packet.get("heartRateSamples", []):
            hr_rows.append({"timestamp": s["timestamp"], "bpm": s["bpm"]})
        for s in packet.get("hrvSamples", []):
            hrv_rows.append({"timestamp": s["timestamp"], "sdnn": s["sdnn"]})
        for s in packet.get("accelerometerSamples", []):
            accel_rows.append({
                "timestamp": s["timestamp"],
                "x": s["x"], "y": s["y"], "z": s["z"],
            })

    heart_rate = pd.DataFrame(hr_rows, columns=["timestamp", "bpm"])
    hrv = pd.DataFrame(hrv_rows, columns=["timestamp", "sdnn"])
    accelerometer = pd.DataFrame(accel_rows, columns=["timestamp", "x", "y", "z"])

    # Sonar features
    sonar_rows = []
    for s in raw.get("sonarFeatures", []):
        sonar_rows.append({
            "timestamp": s["timestamp"],
            "breathing_rate": s.get("breathingRate"),
            "breathing_regularity": s.get("breathingRegularity"),
            "signal_strength": s["signalStrength"],
        })
    sonar = pd.DataFrame(
        sonar_rows,
        columns=["timestamp", "breathing_rate", "breathing_regularity", "signal_strength"],
    )

    # Audio features
    audio_rows = []
    for s in raw.get("audioFeatures", []):
        audio_rows.append({
            "timestamp": s["timestamp"],
            "dominant_frequency": s["dominantFrequency"],
            "spectral_centroid": s["spectralCentroid"],
            "rms_energy": s["rmsEnergy"],
            "zcr": s["zeroCrossingRate"],
            "classification": s["classification"],
        })
    audio = pd.DataFrame(
        audio_rows,
        columns=["timestamp", "dominant_frequency", "spectral_centroid", "rms_energy", "zcr", "classification"],
    )

    # Sleep stages
    stage_rows = []
    for s in raw.get("sleepStages", []):
        stage_rows.append({
            "start": s["startTimestamp"],
            "end": s["endTimestamp"],
            "stage": s["stage"],
        })
    sleep_stages = pd.DataFrame(stage_rows, columns=["start", "end", "stage"])

    # Sort all by timestamp
    if not heart_rate.empty:
        heart_rate = heart_rate.sort_values("timestamp").reset_index(drop=True)
    if not hrv.empty:
        hrv = hrv.sort_values("timestamp").reset_index(drop=True)
    if not accelerometer.empty:
        accelerometer = accelerometer.sort_values("timestamp").reset_index(drop=True)
    if not sonar.empty:
        sonar = sonar.sort_values("timestamp").reset_index(drop=True)
    if not audio.empty:
        audio = audio.sort_values("timestamp").reset_index(drop=True)
    if not sleep_stages.empty:
        sleep_stages = sleep_stages.sort_values("start").reset_index(drop=True)

    return SleepSessionData(
        session_id=raw["id"],
        start_time=start_time,
        end_time=end_time,
        duration_hours=duration_hours,
        heart_rate=heart_rate,
        hrv=hrv,
        accelerometer=accelerometer,
        sonar=sonar,
        audio=audio,
        sleep_stages=sleep_stages,
        metadata=raw.get("metadata", {}),
    )


def load_all_sessions(directory: str | Path) -> list[SleepSessionData]:
    """Load all JSON session files from a directory, sorted by start time.

    Args:
        directory: Path to directory containing session JSON files.

    Returns:
        List of SleepSessionData sorted by start_time.
    """
    directory = Path(directory)
    sessions = []
    for json_file in sorted(directory.glob("*.json")):
        try:
            sessions.append(load_session(json_file))
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: skipping {json_file.name}: {e}")
    sessions.sort(key=lambda s: s.start_time)
    return sessions


# ---------------------------------------------------------------------------
# Mock data generator
# ---------------------------------------------------------------------------

# Sleep stage parameters: (hr_mean, hr_std, hrv_mean, hrv_std,
#                          motion_mean, motion_std, br_mean, br_std, br_reg_mean, br_reg_std)
_STAGE_PARAMS = {
    "awake":     (80, 8,  35, 8,  0.25, 0.15, 18, 3,  0.4, 0.15),
    "remSleep":  (72, 7,  40, 8,  0.04, 0.03, 17, 3,  0.5, 0.15),
    "coreLight": (66, 5,  45, 8,  0.06, 0.04, 15, 2,  0.7, 0.10),
    "deepSleep": (60, 3,  55, 10, 0.02, 0.01, 14, 1.5, 0.85, 0.08),
    "inBed":     (75, 6,  38, 7,  0.10, 0.08, 16, 2,  0.6, 0.12),
}

# Audio classification probabilities by stage
_AUDIO_PROBS = {
    "awake":     {"silence": 0.1, "breathing": 0.2, "snoring": 0.0, "movement": 0.5, "ambientNoise": 0.2},
    "remSleep":  {"silence": 0.3, "breathing": 0.4, "snoring": 0.05, "movement": 0.15, "ambientNoise": 0.1},
    "coreLight": {"silence": 0.35, "breathing": 0.35, "snoring": 0.1, "movement": 0.1, "ambientNoise": 0.1},
    "deepSleep": {"silence": 0.2, "breathing": 0.3, "snoring": 0.3, "movement": 0.05, "ambientNoise": 0.15},
    "inBed":     {"silence": 0.2, "breathing": 0.3, "snoring": 0.0, "movement": 0.3, "ambientNoise": 0.2},
}


def generate_mock_session(
    duration_hours: float = 8.0,
    seed: int = 42,
    save_json: bool = False,
    output_path: Optional[str | Path] = None,
) -> SleepSessionData:
    """Generate a physiologically plausible synthetic sleep session.

    Creates realistic sleep architecture with ~90-minute ultradian cycles,
    progressive REM lengthening, and stage-appropriate sensor characteristics.

    Args:
        duration_hours: Total session duration in hours.
        seed: Random seed for reproducibility.
        save_json: If True, also write the session as JSON.
        output_path: Where to save JSON. If None, uses a temp file.

    Returns:
        A SleepSessionData with synthetic but realistic data.
    """
    rng = np.random.default_rng(seed)
    total_seconds = duration_hours * 3600
    session_id = str(uuid.uuid4())
    start_time = datetime(2025, 3, 15, 23, 0, 0, tzinfo=timezone.utc)
    end_time = start_time + timedelta(seconds=total_seconds)

    # -----------------------------------------------------------------------
    # 1. Generate sleep architecture (stage timeline)
    # -----------------------------------------------------------------------
    stages = _generate_sleep_architecture(total_seconds, rng)

    # -----------------------------------------------------------------------
    # 2. Generate sensor data for each stage segment
    # -----------------------------------------------------------------------
    hr_rows = []
    hrv_rows = []
    accel_rows = []
    sonar_rows = []
    audio_rows = []

    for stage_start, stage_end, stage_name in stages:
        params = _STAGE_PARAMS[stage_name]
        hr_mean, hr_std = params[0], params[1]
        hrv_mean, hrv_std = params[2], params[3]
        motion_mean, motion_std = params[4], params[5]
        br_mean, br_std = params[6], params[7]
        br_reg_mean, br_reg_std = params[8], params[9]

        # Heart rate: ~5 second intervals
        t = stage_start
        while t < stage_end:
            bpm = rng.normal(hr_mean, hr_std)
            bpm = float(np.clip(bpm, 40, 120))
            hr_rows.append({"timestamp": round(t, 2), "bpm": round(bpm, 1)})
            t += rng.uniform(4, 6)  # ~5s ± jitter

        # HRV: ~5 minute intervals
        t = stage_start
        while t < stage_end:
            sdnn = rng.normal(hrv_mean, hrv_std)
            sdnn = float(np.clip(sdnn, 10, 150))
            hrv_rows.append({"timestamp": round(t, 2), "sdnn": round(sdnn, 1)})
            t += rng.uniform(270, 330)  # ~300s ± jitter

        # Accelerometer: 10 Hz (decimated)
        t = stage_start
        while t < stage_end:
            magnitude = abs(rng.normal(motion_mean, motion_std))
            # Random direction on unit sphere, scaled by magnitude
            theta = rng.uniform(0, 2 * np.pi)
            phi = rng.uniform(0, np.pi)
            x = float(magnitude * np.sin(phi) * np.cos(theta))
            y = float(magnitude * np.sin(phi) * np.sin(theta))
            z = float(1.0 + magnitude * np.cos(phi))  # +1G gravity
            accel_rows.append({
                "timestamp": round(t, 3),
                "x": round(x, 4), "y": round(y, 4), "z": round(z, 4),
            })
            t += 0.1  # 10 Hz

        # Sonar features: ~2 second intervals
        t = stage_start
        while t < stage_end:
            breathing_rate = rng.normal(br_mean, br_std)
            breathing_rate = float(np.clip(breathing_rate, 8, 30))
            breathing_regularity = rng.normal(br_reg_mean, br_reg_std)
            breathing_regularity = float(np.clip(breathing_regularity, 0, 1))
            signal_strength = float(rng.normal(-35, 5))  # dB
            sonar_rows.append({
                "timestamp": round(t, 2),
                "breathingRate": round(breathing_rate, 1),
                "breathingRegularity": round(breathing_regularity, 3),
                "signalStrength": round(signal_strength, 1),
            })
            t += rng.uniform(1.8, 2.2)

        # Audio features: ~5 second intervals
        audio_probs = _AUDIO_PROBS[stage_name]
        t = stage_start
        while t < stage_end:
            classification = rng.choice(
                list(audio_probs.keys()),
                p=list(audio_probs.values()),
            )
            rms = float(rng.normal(-40 if classification == "silence" else -25, 5))
            zcr = float(np.clip(rng.normal(0.05, 0.02), 0, 1))
            centroid = float(np.clip(rng.normal(1500, 500), 100, 8000))
            dom_freq = float(np.clip(rng.normal(500, 200), 50, 5000))
            audio_rows.append({
                "timestamp": round(t, 2),
                "dominantFrequency": round(dom_freq, 1),
                "spectralCentroid": round(centroid, 1),
                "rmsEnergy": round(rms, 1),
                "zeroCrossingRate": round(zcr, 4),
                "classification": classification,
            })
            t += rng.uniform(4.5, 5.5)

    # -----------------------------------------------------------------------
    # 3. Build sleep stages DataFrame
    # -----------------------------------------------------------------------
    stage_df_rows = [
        {"start": round(s, 2), "end": round(e, 2), "stage": name}
        for s, e, name in stages
    ]

    # -----------------------------------------------------------------------
    # 4. Assemble into SleepSessionData
    # -----------------------------------------------------------------------
    heart_rate = pd.DataFrame(hr_rows).sort_values("timestamp").reset_index(drop=True)
    hrv_df = pd.DataFrame(hrv_rows).sort_values("timestamp").reset_index(drop=True)
    accel_df = pd.DataFrame(accel_rows).sort_values("timestamp").reset_index(drop=True)

    sonar_df = pd.DataFrame(sonar_rows).sort_values("timestamp").reset_index(drop=True)
    # Rename to Python conventions for the SleepSessionData container
    sonar_df = sonar_df.rename(columns={
        "breathingRate": "breathing_rate",
        "breathingRegularity": "breathing_regularity",
        "signalStrength": "signal_strength",
    })

    audio_df = pd.DataFrame(audio_rows).sort_values("timestamp").reset_index(drop=True)
    audio_df = audio_df.rename(columns={
        "dominantFrequency": "dominant_frequency",
        "spectralCentroid": "spectral_centroid",
        "rmsEnergy": "rms_energy",
        "zeroCrossingRate": "zcr",
    })

    sleep_stages = pd.DataFrame(stage_df_rows)

    metadata = {
        "appVersion": "0.1",
        "watchModel": "Watch7,3",
        "iphoneModel": "iPhone16,1",
        "osVersionWatch": "11.0.0",
        "osVersioniOS": "18.0.0",
        "watchBatteryAtStart": 0.85,
        "watchBatteryAtEnd": 0.42,
        "phoneBatteryAtStart": 0.90,
        "phoneBatteryAtEnd": 0.65,
        "totalPacketsReceived": len(hr_rows) // 6,  # Approximate
        "totalPacketsExpected": int(total_seconds / 30),
        "connectivityDropCount": int(rng.integers(0, 5)),
    }

    session = SleepSessionData(
        session_id=session_id,
        start_time=start_time,
        end_time=end_time,
        duration_hours=duration_hours,
        heart_rate=heart_rate,
        hrv=hrv_df,
        accelerometer=accel_df,
        sonar=sonar_df,
        audio=audio_df,
        sleep_stages=sleep_stages,
        metadata=metadata,
    )

    # Optionally save as JSON (matching Swift export format)
    if save_json:
        _save_mock_as_json(session, hr_rows, hrv_rows, accel_rows,
                           sonar_rows, audio_rows, stage_df_rows,
                           metadata, output_path)

    return session


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_sleep_architecture(
    total_seconds: float,
    rng: np.random.Generator,
) -> list[tuple[float, float, str]]:
    """Generate a realistic sleep stage timeline.

    Models ~90-minute ultradian cycles with:
    - Progressive REM lengthening across the night
    - Deep sleep concentrated in early cycles
    - Brief awakenings between cycles
    - Falling asleep and waking up transitions

    Returns:
        List of (start_seconds, end_seconds, stage_name) tuples.
    """
    stages: list[tuple[float, float, str]] = []
    t = 0.0

    # Sleep onset: awake → inBed → light sleep
    onset_awake = rng.uniform(5 * 60, 15 * 60)  # 5-15 min awake
    stages.append((t, t + onset_awake, "inBed"))
    t += onset_awake

    # Ultradian cycles
    cycle_num = 0
    while t < total_seconds - 30 * 60:  # Stop 30 min before end
        cycle_num += 1
        cycle_duration = rng.uniform(80, 100) * 60  # ~90 min cycle

        # Light sleep phase
        light1_dur = rng.uniform(10, 20) * 60
        if t + light1_dur > total_seconds:
            break
        stages.append((t, t + light1_dur, "coreLight"))
        t += light1_dur

        # Deep sleep (more in early cycles, less in later ones)
        deep_base = max(5, 25 - cycle_num * 5)  # Decreases each cycle
        deep_dur = rng.uniform(deep_base * 0.5, deep_base * 1.5) * 60
        if t + deep_dur > total_seconds:
            break
        stages.append((t, t + deep_dur, "deepSleep"))
        t += deep_dur

        # Transition light sleep
        light2_dur = rng.uniform(5, 15) * 60
        if t + light2_dur > total_seconds:
            break
        stages.append((t, t + light2_dur, "coreLight"))
        t += light2_dur

        # REM phase (lengthens each cycle: ~5 min first, ~30 min last)
        rem_base = min(5 + cycle_num * 5, 35)
        rem_dur = rng.uniform(rem_base * 0.7, rem_base * 1.3) * 60
        if t + rem_dur > total_seconds:
            break
        stages.append((t, t + rem_dur, "remSleep"))
        t += rem_dur

        # Brief awakening between cycles (~1-3 min, not every cycle)
        if rng.random() < 0.6:
            wake_dur = rng.uniform(30, 180)
            if t + wake_dur < total_seconds:
                stages.append((t, t + wake_dur, "awake"))
                t += wake_dur

    # Fill remaining time with light sleep → awakening
    remaining = total_seconds - t
    if remaining > 5 * 60:
        light_end = remaining - rng.uniform(3, 10) * 60
        stages.append((t, t + light_end, "coreLight"))
        t += light_end
    if t < total_seconds:
        stages.append((t, total_seconds, "awake"))

    return stages


def _parse_iso8601(date_string: str) -> datetime:
    """Parse ISO 8601 date string as produced by Swift's .iso8601 encoder."""
    # Swift's ISO8601DateFormatter produces: "2025-03-15T23:00:00Z"
    # Python's fromisoformat handles this in 3.11+, but let's be safe
    date_string = date_string.replace("Z", "+00:00")
    return datetime.fromisoformat(date_string)


def _save_mock_as_json(
    session: SleepSessionData,
    hr_rows: list[dict],
    hrv_rows: list[dict],
    accel_rows: list[dict],
    sonar_rows: list[dict],
    audio_rows: list[dict],
    stage_rows: list[dict],
    metadata: dict,
    output_path: Optional[str | Path],
) -> Path:
    """Save a mock session as JSON matching the Swift export format.

    Reconstructs the nested watchPackets structure with 30-second batches.
    """
    batch_interval = 30.0  # seconds
    total_seconds = session.duration_hours * 3600

    # Group HR/HRV/accel into 30-second batches (simulating watch packets)
    packets = []
    batch_idx = 0
    t = 0.0
    while t < total_seconds:
        batch_end = t + batch_interval
        hr_batch = [r for r in hr_rows if t <= r["timestamp"] < batch_end]
        hrv_batch = [r for r in hrv_rows if t <= r["timestamp"] < batch_end]
        accel_batch = [r for r in accel_rows if t <= r["timestamp"] < batch_end]

        if hr_batch or hrv_batch or accel_batch:
            captured_at = session.start_time + timedelta(seconds=t + batch_interval)
            packets.append({
                "sessionID": session.session_id,
                "batchIndex": batch_idx,
                "capturedAt": captured_at.isoformat().replace("+00:00", "Z"),
                "heartRateSamples": hr_batch,
                "hrvSamples": hrv_batch,
                "accelerometerSamples": accel_batch,
            })
            batch_idx += 1
        t += batch_interval

    # Build sleep stage labels with Swift field names
    sleep_stages_json = [
        {
            "startTimestamp": r["start"],
            "endTimestamp": r["end"],
            "stage": r["stage"],
        }
        for r in stage_rows
    ]

    # Assemble full JSON matching SleepSession Swift struct
    session_json = {
        "id": session.session_id,
        "startDate": session.start_time.isoformat().replace("+00:00", "Z"),
        "endDate": session.end_time.isoformat().replace("+00:00", "Z") if session.end_time else None,
        "watchPackets": packets,
        "sonarFeatures": sonar_rows,
        "audioFeatures": audio_rows,
        "sleepStages": sleep_stages_json,
        "metadata": metadata,
    }

    if output_path is None:
        output_path = Path(tempfile.mkdtemp()) / "lullaby_session_mock.json"
    else:
        output_path = Path(output_path)

    with open(output_path, "w") as f:
        json.dump(session_json, f, indent=2, sort_keys=True)

    return output_path
