"""Waking-arc wiring — arbiter-sourced meta reaches the L1 sink (no mic, no DB)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))

from core.bus.bus import TOPIC_SIGNAL, MessageBus  # noqa: E402
from core.protocol.enums import MetaContext  # noqa: E402
from fusion.meta_arbiter import MetaContextArbiter  # noqa: E402
from runtime import waking_arc  # noqa: E402
from sensors.audio_adapter import AudioBusSink  # noqa: E402


def _run_captured() -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    waking_arc.run(listen_fn=lambda **kwargs: calls.append(kwargs))
    (kwargs,) = calls
    return kwargs


def test_run_passes_arbiter_reader_to_listener():
    kwargs = _run_captured()
    assert isinstance(kwargs["bus"], MessageBus)
    meta_source = kwargs["meta_context"]
    assert callable(meta_source)
    assert meta_source() is MetaContext.WAKING
    assert isinstance(meta_source.__self__, MetaContextArbiter)


def test_arbiter_sourced_meta_reaches_the_sink():
    kwargs = _run_captured()
    meta_source = kwargs["meta_context"]
    arbiter: MetaContextArbiter = meta_source.__self__

    bus = MessageBus()
    got: list[Any] = []
    bus.subscribe(TOPIC_SIGNAL, got.append)
    sink = AudioBusSink(bus, meta_context=meta_source)
    now = datetime.now(timezone.utc)

    sink.write_social(user_id="u", recorded_at=now, speaker="self",
                      num_speakers=1, vad_active=True)
    assert got[-1].meta_context is MetaContext.WAKING

    sleeping = {
        "sleep_stage": {"value": {"label": "deep", "active": True},
                        "confidence": 0.95, "source": "t", "timestamp": "t"},
    }
    for _ in range(arbiter.sleep_entry_observations):
        arbiter.observe(sleeping)
    sink.write_social(user_id="u", recorded_at=now, speaker="none",
                      num_speakers=0, vad_active=False)
    assert got[-1].meta_context is MetaContext.SLEEP


def test_constant_meta_context_still_accepted():
    bus = MessageBus()
    got: list[Any] = []
    bus.subscribe(TOPIC_SIGNAL, got.append)
    sink = AudioBusSink(bus, meta_context=MetaContext.WAKING)
    sink.write_social(user_id="u", recorded_at=datetime.now(timezone.utc),
                      speaker="self", num_speakers=1, vad_active=True)
    assert got[-1].meta_context is MetaContext.WAKING
