"""Loopback proof that the hub/satellite entrypoints wire NetworkTransport for real.

Mirrors core/bus/test_network.py's bounded _wait_until polling (never bare
sleeps for sync) so the relay assertions are not flaky. The hub runs the REAL
assembled pipeline; only the leaf seams (axis registry / policy / renderer /
speak) are injected exactly the way core/test_pipeline.py injects them, so no
test path touches DB, LLM, network beyond 127.0.0.1, or audio hardware.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pytest

from core.bus.bus import TOPIC_OUTPUT, TOPIC_SIGNAL, MessageBus
from core.protocol.enums import MetaContext, PayloadType
from core.protocol.envelope import MessageEnvelope
from core.test_pipeline import _fresh_axis_registry, _InterjectPolicy
from output.renderer import StubRenderer
from runtime import hub, satellite
from sensors.contract import DEFAULT_USER_ID
from sensors.eeg_adapter import EEGBusSink, synthesize_eeg_window

_KEY = "test-shared-key-not-a-secret"
_PI_DIR = Path(__file__).resolve().parent.parent.parent / "pi"


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_until(predicate: Callable[[], bool], timeout: float = 3.0, interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ---------------------------------------------------------------------------
# --sensors selection logic (no sockets).
# ---------------------------------------------------------------------------

def test_sensor_registry_is_the_documented_set():
    assert set(satellite.SENSOR_LOOPS) == {"eeg", "audio", "vision", "watch"}


def test_parse_sensors_single():
    assert satellite.parse_sensors("eeg") == ["eeg"]


def test_parse_sensors_strips_and_keeps_order():
    assert satellite.parse_sensors(" vision, eeg ,watch") == ["vision", "eeg", "watch"]


def test_parse_sensors_dedupes_preserving_first():
    assert satellite.parse_sensors("eeg,vision,eeg") == ["eeg", "vision"]


def test_parse_sensors_unknown_raises():
    with pytest.raises(ValueError, match="thermal"):
        satellite.parse_sensors("eeg,thermal")


def test_parse_sensors_empty_raises():
    with pytest.raises(ValueError):
        satellite.parse_sensors(" , ")


# ---------------------------------------------------------------------------
# Env/arg handling (no sockets).
# ---------------------------------------------------------------------------

def test_hub_args_require_key(monkeypatch):
    monkeypatch.delenv(hub.ENV_KEY, raising=False)
    with pytest.raises(SystemExit):
        hub._parse_args([])


def test_hub_args_from_env(monkeypatch):
    monkeypatch.setenv(hub.ENV_HOST, "127.0.0.9")
    monkeypatch.setenv(hub.ENV_PORT, "9911")
    monkeypatch.setenv(hub.ENV_KEY, "k")
    args = hub._parse_args([])
    assert (args.host, args.port, args.key) == ("127.0.0.9", 9911, "k")


def test_satellite_args_require_key(monkeypatch):
    monkeypatch.delenv(satellite.ENV_KEY, raising=False)
    with pytest.raises(SystemExit):
        satellite._parse_args([])


def test_satellite_args_from_env(monkeypatch):
    monkeypatch.setenv(satellite.ENV_URL, "ws://10.0.0.2:9000")
    monkeypatch.setenv(satellite.ENV_KEY, "k")
    args = satellite._parse_args(["--sensors", "vision,watch"])
    assert args.hub_url == "ws://10.0.0.2:9000"
    assert args.key == "k"
    assert satellite.parse_sensors(args.sensors) == ["vision", "watch"]


# ---------------------------------------------------------------------------
# Synthetic edge loops emit on any bus — transport-agnostic, no sockets.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,kind", [
    ("eeg", "eeg_bandpower"),
    ("vision", "visual_scene"),
    ("watch", "biometric_window"),
])
def test_synthetic_sensor_loops_emit_without_sockets(name, kind):
    bus = MessageBus()
    seen: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_SIGNAL, seen.append)
    stop = threading.Event()
    thread = threading.Thread(
        target=satellite.SENSOR_LOOPS[name], args=(bus,),
        kwargs={"user_id": DEFAULT_USER_ID, "stop": stop, "interval": 0.01},
        daemon=True,
    )
    thread.start()
    assert _wait_until(lambda: len(seen) >= 2), f"{name} loop never emitted"
    stop.set()
    thread.join(timeout=2.0)
    assert seen[0].payload.kind == kind
    assert seen[0].meta_context == MetaContext.WAKING


# ---------------------------------------------------------------------------
# The e2e loopback relay — real entrypoint builders, real arc, both directions.
# ---------------------------------------------------------------------------

@pytest.fixture
def linked_runtimes():
    """Hub (full arc, injected leaf seams) + satellite on loopback, both started."""
    port = _free_port()
    spoken: list[str] = []
    hub_bus, hub_link = hub.build_hub(
        host="127.0.0.1", port=port, key=_KEY,
        fusion_registry=_fresh_axis_registry(),
        decision_policy=_InterjectPolicy(),
        renderer=StubRenderer(),
        speak=spoken.append,
    )
    sat_bus, sat_link = satellite.build_satellite_bus(url=f"ws://127.0.0.1:{port}", key=_KEY)
    assert _wait_until(lambda: hub_link.peer_connected and sat_link.peer_connected), \
        "hub and satellite did not connect"
    try:
        yield hub_bus, sat_bus, spoken
    finally:
        sat_link.stop()
        hub_link.stop()


def test_satellite_packet_drives_hub_arc_and_directive_returns(linked_runtimes):
    hub_bus, sat_bus, spoken = linked_runtimes
    hub_signals: list[MessageEnvelope] = []
    hub_outputs: list[MessageEnvelope] = []
    sat_outputs: list[MessageEnvelope] = []
    hub_bus.subscribe(TOPIC_SIGNAL, hub_signals.append)
    hub_bus.subscribe(TOPIC_OUTPUT, hub_outputs.append)
    sat_bus.subscribe(TOPIC_OUTPUT, sat_outputs.append)

    sink = EEGBusSink(sat_bus, meta_context=MetaContext.WAKING)
    sink.write_window(
        user_id=DEFAULT_USER_ID,
        recorded_at=datetime.now(timezone.utc),
        samples=synthesize_eeg_window(seed=7),
    )

    assert _wait_until(lambda: len(hub_signals) == 1), "satellite signal never reached the hub"
    sig = hub_signals[0]
    assert sig.type == PayloadType.SIGNAL
    assert sig.payload.kind == EEGBusSink.KIND
    assert "samples" not in sig.payload.payload  # raw never crossed the wire (#11)

    assert _wait_until(lambda: len(hub_outputs) == 1), "hub arc never produced a directive"
    out = hub_outputs[0]
    assert out.trace_id == sig.trace_id  # one arc, same trace L1->L6
    assert out.payload.channel == "voice"

    assert _wait_until(lambda: len(sat_outputs) == 1), "directive never returned to the satellite"
    assert sat_outputs[0].trace_id == sig.trace_id
    assert sat_outputs[0].payload.text == out.payload.text

    assert _wait_until(lambda: spoken == [out.payload.text]), "hub speaker never spoke"


def test_watch_window_survives_the_wire(linked_runtimes):
    """The datetime-heavy biometric_window payload must JSON-encode at the link."""
    hub_bus, sat_bus, _spoken = linked_runtimes
    received: list[MessageEnvelope] = []
    hub_bus.subscribe(TOPIC_SIGNAL, received.append)

    from sensors.watch_adapter import WatchBusSink, synthesize_biometric_window

    sink = WatchBusSink(sat_bus, meta_context=MetaContext.WAKING)
    window = synthesize_biometric_window(epoch_start_at=datetime.now(timezone.utc), index=1)
    sink.emit_window(**window)

    assert _wait_until(lambda: len(received) == 1), "watch window never crossed the wire"
    assert received[0].payload.kind == "biometric_window"
    assert isinstance(received[0].payload.payload["epoch_start_at"], str)


# ---------------------------------------------------------------------------
# Pi entrypoints.
# ---------------------------------------------------------------------------

def test_pi_daemon_tombstone_exits_1():
    proc = subprocess.run([sys.executable, str(_PI_DIR / "daemon.py")],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 1
    assert "use apps/pi/satellite.py" in proc.stderr + proc.stdout


def test_pi_satellite_entrypoint_resolves_imports():
    proc = subprocess.run([sys.executable, str(_PI_DIR / "satellite.py"), "--help"],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0
    assert "--sensors" in proc.stdout
