from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import serial

from .base import SensorPacket, SensorSource

logger = logging.getLogger(__name__)


class ESP32SerialSource(SensorSource):
    """Reads JSON-line sensor packets from an ESP32 over USB serial.

    Expects newline-delimited JSON on the serial port, matching
    AI_PI_CONTRACT.md's sensor packet format:
        {"recorded_at": "...", "kind": "...", "value": 68.2, "source": "..."}

    If the ESP32 omits `recorded_at` (low-clock-accuracy boards), we stamp it
    with the Pi's current time on arrival. ESP32 firmware should still send
    its own timestamp where possible.
    """

    name = "esp32_serial"

    def __init__(self, port: str, baud: int = 115200, reconnect_delay: float = 2.0) -> None:
        super().__init__()
        self.port = port
        self.baud = baud
        self.reconnect_delay = reconnect_delay
        self.name = f"esp32_serial({port})"

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                with serial.Serial(self.port, self.baud, timeout=1.0) as ser:
                    logger.info("%s connected", self.name)
                    self._stream(ser)
            except serial.SerialException as e:
                logger.warning("%s disconnected (%s) — reconnecting in %.1fs", self.name, e, self.reconnect_delay)
                time.sleep(self.reconnect_delay)

    def _stream(self, ser: "serial.Serial") -> None:
        while not self._stop_event.is_set():
            try:
                raw = ser.readline()
            except serial.SerialException as e:
                logger.warning("%s read error: %s", self.name, e)
                return
            if not raw:
                continue
            try:
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                obj = json.loads(line)
            except (ValueError, json.JSONDecodeError) as e:
                logger.debug("%s skipped malformed line: %r (%s)", self.name, raw[:80], e)
                continue

            try:
                kind = obj["kind"]
                value = float(obj["value"])
                source = obj.get("source", "esp32")
                ts_raw = obj.get("recorded_at")
                if ts_raw is None:
                    recorded_at = datetime.now(timezone.utc)
                else:
                    recorded_at = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except (KeyError, ValueError, TypeError) as e:
                logger.debug("%s skipped invalid packet %r (%s)", self.name, obj, e)
                continue

            self._emit(SensorPacket(
                recorded_at=recorded_at,
                kind=kind,
                value=value,
                source=source,
            ))
