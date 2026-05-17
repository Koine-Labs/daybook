"""Pluggable sensor sources for the Pi daemon.

Each source runs in its own thread, reading or generating SensorPackets and
pushing them into a thread-safe queue. The daemon's processor thread drains the
queue, writes packets to Postgres, and feeds the classifier.
"""
from .base import SensorSource, SensorPacket  # noqa: F401
from .mock import MockSensorSource  # noqa: F401

try:
    from .esp32_serial import ESP32SerialSource  # noqa: F401
except ImportError:
    # pyserial may not be installed in some dev environments
    pass


def build_sensor(spec: str) -> SensorSource:
    """Parse a sensor spec string and return the corresponding SensorSource.

    Spec format:
        "mock"                 → MockSensorSource (fake HR)
        "esp32:/dev/ttyUSB0"   → ESP32SerialSource on that port
        (future) "esp32_cam:..", "pi_mic", ...
    """
    if spec == "mock":
        return MockSensorSource()
    if spec.startswith("esp32:"):
        port = spec.split(":", 1)[1]
        return ESP32SerialSource(port=port)
    raise ValueError(f"Unknown sensor spec: {spec!r}")
