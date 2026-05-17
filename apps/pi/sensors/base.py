from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from queue import Queue

logger = logging.getLogger(__name__)


@dataclass
class SensorPacket:
    recorded_at: datetime  # tz-aware UTC
    kind: str              # heart_rate, hrv, respiratory_rate, spo2, eeg_*, motion_*
    value: float
    source: str            # short identifier (e.g. "esp32_bioamp_pill", "mock_hr")


class SensorSource(ABC):
    """Base class for sensor data producers.

    Subclasses implement `_run_loop` which pushes packets to `self._queue` until
    `self._stop_event` is set.
    """

    name: str = "sensor"

    def __init__(self) -> None:
        self._queue: Queue[SensorPacket] | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def attach(self, queue: Queue[SensorPacket]) -> None:
        self._queue = queue

    def start(self) -> None:
        if self._queue is None:
            raise RuntimeError(f"{self.name}: attach() a queue before start()")
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._safe_run, name=self.name, daemon=True)
        self._thread.start()
        logger.info("%s started", self.name)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("%s did not stop within %.1fs", self.name, timeout)
            else:
                logger.info("%s stopped", self.name)
        self._thread = None

    def _safe_run(self) -> None:
        try:
            self._run_loop()
        except Exception:
            logger.exception("%s crashed", self.name)

    def _emit(self, packet: SensorPacket) -> None:
        assert self._queue is not None
        self._queue.put(packet)

    @abstractmethod
    def _run_loop(self) -> None:
        """Push packets to self._queue until self._stop_event is set."""
