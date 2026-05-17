from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone

from .base import SensorPacket, SensorSource

logger = logging.getLogger(__name__)


class MockSensorSource(SensorSource):
    """Generates plausible HR + respiratory_rate at sleep-like cadence.

    Useful for end-to-end testing without any physical hardware.
    Mirrors the sparsity profile of Apple Watch HK exports (~14 HR readings/hour)
    and occasionally bumps HR to simulate REM windows.
    """

    name = "mock"

    def __init__(
        self,
        hr_interval_seconds: float = 90.0,
        resp_interval_seconds: float = 600.0,
        rem_window_minutes: tuple[int, ...] = (95, 240, 380, 510),  # REM at typical cycle times
        rem_window_duration_minutes: float = 20.0,
        fast_forward: bool = False,
    ) -> None:
        super().__init__()
        self.hr_interval = hr_interval_seconds
        self.resp_interval = resp_interval_seconds
        self.rem_windows = rem_window_minutes
        self.rem_duration = rem_window_duration_minutes
        self.fast_forward = fast_forward
        self._t0 = datetime.now(timezone.utc)

    def _in_rem_window(self, elapsed_minutes: float) -> bool:
        return any(
            start <= elapsed_minutes < start + self.rem_duration
            for start in self.rem_windows
        )

    def _gen_hr(self, elapsed_minutes: float) -> float:
        base = 55.0 + random.gauss(0, 1.5)
        if self._in_rem_window(elapsed_minutes):
            base += 10.0 + random.gauss(0, 3.0)
        return max(40.0, base)

    def _gen_resp(self, elapsed_minutes: float) -> float:
        base = 13.0 + random.gauss(0, 0.5)
        if self._in_rem_window(elapsed_minutes):
            base += 2.0 + random.gauss(0, 0.8)
        return max(8.0, base)

    def _run_loop(self) -> None:
        next_hr = time.monotonic()
        next_resp = time.monotonic()
        time_scale = 60.0 if self.fast_forward else 1.0  # 1 real second = 1 "real" second (or 1 minute if FF)

        while not self._stop_event.is_set():
            now_mono = time.monotonic()
            now_dt = datetime.now(timezone.utc)
            elapsed_minutes = (now_dt - self._t0).total_seconds() / 60.0 * time_scale

            if now_mono >= next_hr:
                hr = self._gen_hr(elapsed_minutes)
                self._emit(SensorPacket(
                    recorded_at=now_dt,
                    kind="heart_rate",
                    value=hr,
                    source="mock_hr",
                ))
                next_hr = now_mono + (self.hr_interval / time_scale)

            if now_mono >= next_resp:
                resp = self._gen_resp(elapsed_minutes)
                self._emit(SensorPacket(
                    recorded_at=now_dt,
                    kind="respiratory_rate",
                    value=resp,
                    source="mock_resp",
                ))
                next_resp = now_mono + (self.resp_interval / time_scale)

            time.sleep(0.5)
