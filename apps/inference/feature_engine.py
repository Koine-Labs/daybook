"""Real-time feature computation from raw sensor data."""

from __future__ import annotations

import math
from collections import deque
from datetime import datetime

import numpy as np

AUDIO_CLASSES = ["breathing", "silence", "snoring", "movement"]


class FeatureEngine:
    def __init__(self, expected_features: list[str], max_history: int = 10) -> None:
        self._expected = expected_features
        self._history: deque[dict[str, float]] = deque(maxlen=max_history)
        self._epoch_count = 0
        self._session_start: datetime | None = None
        self._assumed_duration_hours = 8.0

    def compute(self, raw_data: dict, timestamp: str) -> dict[str, float]:
        try:
            ts = timestamp.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts)
            if self._session_start is None:
                self._session_start = dt
        except (ValueError, AttributeError):
            dt = None

        base = self._compute_base_features(raw_data, timestamp)
        self._history.append(base)
        self._epoch_count += 1

        temporal = self._compute_temporal_features(base)
        features = {**base, **temporal}

        result = {}
        for name in self._expected:
            result[name] = features.get(name, float("nan"))
        return result

    def _compute_base_features(self, raw: dict, timestamp: str) -> dict[str, float]:
        features: dict[str, float] = {}

        # Heart Rate
        hr = raw.get("hr_samples", [])
        if hr:
            arr = np.array(hr, dtype=np.float64)
            features["hr_mean"] = float(np.mean(arr))
            features["hr_std"] = float(np.std(arr)) if len(arr) > 1 else 0.0
            features["hr_min"] = float(np.min(arr))
            features["hr_max"] = float(np.max(arr))
            features["hr_range"] = float(np.max(arr) - np.min(arr))
        else:
            for k in ("hr_mean", "hr_std", "hr_min", "hr_max", "hr_range"):
                features[k] = float("nan")

        # HRV
        hrv = raw.get("hrv_samples", [])
        features["hrv_mean"] = float(np.mean(hrv)) if hrv else float("nan")

        # Accelerometer magnitude
        ax = raw.get("accel_x", [])
        ay = raw.get("accel_y", [])
        az = raw.get("accel_z", [])
        n = min(len(ax), len(ay), len(az))
        if n > 0:
            mag = np.sqrt(np.array(ax[:n], dtype=np.float64)**2 + np.array(ay[:n], dtype=np.float64)**2 + np.array(az[:n], dtype=np.float64)**2)
            motion = np.abs(mag - 1.0)
            features["accel_mag_mean"] = float(np.mean(motion))
            features["accel_mag_std"] = float(np.std(motion)) if n > 1 else 0.0
            features["accel_mag_max"] = float(np.max(motion))
        else:
            for k in ("accel_mag_mean", "accel_mag_std", "accel_mag_max"):
                features[k] = float("nan")

        # Sonar
        features["breathing_rate_mean"] = raw.get("sonar_breathing_rate") or float("nan")
        features["breathing_regularity_mean"] = float("nan")
        features["signal_strength_mean"] = raw.get("sonar_amplitude") or float("nan")

        # Audio
        features["rms_energy_mean"] = raw.get("audio_rms") or float("nan")
        features["spectral_centroid_mean"] = raw.get("audio_spectral_centroid") or float("nan")

        # Audio one-hot
        audio_class = raw.get("audio_class", "")
        for cls in AUDIO_CLASSES:
            features[f"audio_is_{cls}"] = 1.0 if audio_class == cls else 0.0

        # Time of night (session-relative, matching training pipeline)
        try:
            ts = timestamp.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts)
            if self._session_start is not None:
                elapsed = (dt - self._session_start).total_seconds()
                session_duration = self._assumed_duration_hours * 3600
                features["time_of_night"] = min(max(elapsed / session_duration, 0.0), 1.0)
            else:
                features["time_of_night"] = 0.0
        except (ValueError, AttributeError):
            features["time_of_night"] = float("nan")

        return features

    def _compute_temporal_features(self, current: dict[str, float]) -> dict[str, float]:
        features: dict[str, float] = {}
        base_keys = ["hr_mean", "hrv_mean", "accel_mag_mean", "breathing_rate_mean", "breathing_regularity_mean"]
        history_list = list(self._history)
        n = len(history_list)

        for key in base_keys:
            # Deltas
            if n >= 2:
                prev = history_list[-2].get(key, float("nan"))
                curr = current.get(key, float("nan"))
                if not (math.isnan(prev) or math.isnan(curr)):
                    features[f"{key}_delta"] = curr - prev
                else:
                    features[f"{key}_delta"] = float("nan")
            else:
                features[f"{key}_delta"] = float("nan")

            # Rolling windows
            for win in (3, 5):
                if n >= win:
                    vals = [h.get(key, float("nan")) for h in list(history_list)[-win:]]
                    valid = [v for v in vals if not math.isnan(v)]
                    if valid:
                        arr = np.array(valid)
                        features[f"{key}_roll{win}_mean"] = float(np.mean(arr))
                        features[f"{key}_roll{win}_std"] = float(np.std(arr))
                    else:
                        features[f"{key}_roll{win}_mean"] = float("nan")
                        features[f"{key}_roll{win}_std"] = float("nan")
                else:
                    features[f"{key}_roll{win}_mean"] = float("nan")
                    features[f"{key}_roll{win}_std"] = float("nan")

        # Inter-epoch HRV
        for win in (3, 5):
            if n >= win:
                hr_vals = [h.get("hr_mean", float("nan")) for h in list(history_list)[-win:]]
                valid = [v for v in hr_vals if not math.isnan(v)]
                if len(valid) >= 2:
                    features[f"hr_mean_iev_{win}"] = float(np.std(valid))
                else:
                    features[f"hr_mean_iev_{win}"] = float("nan")
            else:
                features[f"hr_mean_iev_{win}"] = float("nan")

        return features
