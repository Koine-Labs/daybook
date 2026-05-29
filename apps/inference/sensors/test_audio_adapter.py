"""L1 audio producer + privacy arc — hardware-free, network-free, DB-free.

Drives the REUSED voice.continuous.ContinuousProcessor with injected fake
extractors (no models, no mic) through an AudioBusSink, and asserts the
privacy-gated SignalPackets that land on TOPIC_SIGNAL. The §3.5 tests extend the
arc through L2 (features.participant) and L3 (fusion.participant) on one bus.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

INF_DIR = Path(__file__).resolve().parent.parent
if str(INF_DIR) not in sys.path:
    sys.path.insert(0, str(INF_DIR))
# voice/ lives under apps/, one level above apps/inference.
APPS_DIR = INF_DIR.parent
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from core.bus.bus import TOPIC_BELIEF, TOPIC_FEATURE, TOPIC_SIGNAL, MessageBus  # noqa: E402
from core.protocol.envelope import MessageEnvelope  # noqa: E402
from core.protocol.payloads import FeatureSnapshot, SignalPacket  # noqa: E402
from sensors.audio_adapter import AUDIO_SOURCE, AudioBusSink  # noqa: E402
from voice.continuous import ContinuousProcessor  # noqa: E402

SR = 16000
WINDOW = np.ones(SR, dtype=np.float32)
PROSODY = {"energy": 0.4, "pitch_mean_hz": 120.0, "pitch_std_hz": 8.0,
           "speaking_rate_wpm": 130.0, "tone": "calm"}


def _proc(bus: MessageBus, *, speakers: list[str],
          ambient: list[dict] | None = None) -> ContinuousProcessor:
    sink = AudioBusSink(bus)
    return ContinuousProcessor(
        identify_speakers=lambda a, sr: list(speakers),
        prosody_of=lambda a, sr: dict(PROSODY),
        ambient_of=lambda a, sr: list(ambient or []),
        write_social=sink.write_social,
        write_prosody=sink.write_prosody,
        write_ambient=sink.write_ambient,
    )


def _collect_signals(bus: MessageBus) -> list[MessageEnvelope]:
    got: list[MessageEnvelope] = []
    bus.subscribe(TOPIC_SIGNAL, got.append)
    return got


def _kinds(envs: list[MessageEnvelope]) -> list[str]:
    return [e.payload.kind for e in envs]


def test_self_speech_emits_social_and_prosody_on_bus():
    bus = MessageBus()
    got = _collect_signals(bus)
    proc = _proc(bus, speakers=["self"])

    proc.process_window(WINDOW, SR, vad_active=True, now=datetime.now(timezone.utc))

    assert set(_kinds(got)) == {"audio_social_context", "audio_prosody"}
    for e in got:
        assert isinstance(e.payload, SignalPacket)
        assert e.payload.modality == "audio"
        assert e.payload.intent == "continuous"
        assert e.payload.source == AUDIO_SOURCE
    social = next(e.payload for e in got if e.payload.kind == "audio_social_context")
    assert social.payload["speaker"] == "self"
    prosody = next(e.payload for e in got if e.payload.kind == "audio_prosody")
    assert prosody.payload["tone"] == "calm"


def test_other_voice_emits_presence_only():
    """PRIVACY (load-bearing): a non-self speaker -> ONLY the presence marker."""
    bus = MessageBus()
    got = _collect_signals(bus)
    proc = _proc(bus, speakers=["self", "other"])

    proc.process_window(WINDOW, SR, vad_active=True, now=datetime.now(timezone.utc))

    assert _kinds(got) == ["audio_social_context"]
    assert got[0].payload.payload["speaker"] == "both"
    assert "audio_prosody" not in _kinds(got)
    assert "audio_ambient" not in _kinds(got)


def test_unknown_speaker_fails_safe_to_suppressed():
    """#1 fail-safe: unknown -> classified as other -> suppressed -> presence only."""
    bus = MessageBus()
    got = _collect_signals(bus)
    proc = _proc(bus, speakers=["unknown"])

    proc.process_window(WINDOW, SR, vad_active=True, now=datetime.now(timezone.utc))

    assert _kinds(got) == ["audio_social_context"]
    assert got[0].payload.payload["speaker"] == "other"


def test_silence_emits_ambient_marker():
    bus = MessageBus()
    got = _collect_signals(bus)
    proc = _proc(bus, speakers=[], ambient=[{"class": "Silence", "score": 0.9}])

    proc.process_window(WINDOW, SR, vad_active=False, now=datetime.now(timezone.utc))

    assert set(_kinds(got)) == {"audio_social_context", "audio_ambient"}
    social = next(e.payload for e in got if e.payload.kind == "audio_social_context")
    assert social.payload["speaker"] == "none"
    ambient = next(e.payload for e in got if e.payload.kind == "audio_ambient")
    assert ambient.payload["top_classes"][0]["class"] == "Silence"
    assert "audio_prosody" not in _kinds(got)


def test_consent_scope_and_no_raw_audio():
    bus = MessageBus()
    got = _collect_signals(bus)
    proc = _proc(bus, speakers=["self"])

    proc.process_window(WINDOW, SR, vad_active=True, now=datetime.now(timezone.utc))

    # consent_scope from the AUDIO -> voice mapping (mic_continuous_v1).
    assert got[0].consent_scope == "mic_continuous_v1"
    # Semantic-first (#11): no raw audio / bytes / numpy ever rides the bus.
    for e in got:
        payload = e.payload.payload
        assert "audio" not in payload
        for v in payload.values():
            assert not isinstance(v, (bytes, bytearray, np.ndarray))


def test_transport_agnostic_shape():
    """Envelope serializes cleanly -> wire-ready for NetworkTransport later."""
    bus = MessageBus()
    got = _collect_signals(bus)
    proc = _proc(bus, speakers=["self"])

    proc.process_window(WINDOW, SR, vad_active=True, now=datetime.now(timezone.utc))

    d = got[0].to_dict()
    assert d["payload"]["modality"] == "audio"
    assert d["payload"]["source"] == AUDIO_SOURCE


# --- §3.5 full producer -> L1 -> L2 -> L3 arc on a single bus -----------------

def _wire_l2_l3(bus: MessageBus, now: datetime):
    """Wire L2 + L3 onto the bus; record the audio_social_context belief value at
    each TOPIC_BELIEF publish. The BeliefState is mutable + reused per user, so we
    snapshot the value (not the aliased object) the instant each belief lands."""
    from features.participant import register as register_l2
    from fusion.participant import register as register_l3

    features: list[MessageEnvelope] = []
    social_categories: list[dict] = []

    def _on_belief(env: MessageEnvelope) -> None:
        est = env.payload.get("audio_social_context", now=now)
        if est is not None:
            social_categories.append(dict(est.value, _source=est.source))

    bus.subscribe(TOPIC_FEATURE, features.append)
    bus.subscribe(TOPIC_BELIEF, _on_belief)
    register_l2(bus)
    register_l3(bus)
    return features, social_categories


def test_full_audio_arc_self_present():
    now = datetime.now(timezone.utc)
    bus = MessageBus()
    features, social_categories = _wire_l2_l3(bus, now)
    proc = _proc(bus, speakers=["self"])

    proc.process_window(WINDOW, SR, vad_active=True, now=now)

    social_feats = [
        e.payload for e in features
        if isinstance(e.payload, FeatureSnapshot)
        and e.payload.payload.get("kind") == "audio_social_context"
    ]
    assert social_feats and social_feats[0].payload["social_category"] == "alone"

    # The live social-context belief reached L3 (captured at publish time).
    assert {"category": "alone", "_source": "L3.fusion.audio_social_context.v1.live"} in social_categories


def test_full_audio_arc_other_present_only_presence():
    now = datetime.now(timezone.utc)
    bus = MessageBus()
    features, social_categories = _wire_l2_l3(bus, now)
    signals = _collect_signals(bus)
    proc = _proc(bus, speakers=["self", "other"])

    proc.process_window(WINDOW, SR, vad_active=True, now=now)

    # Only ONE SignalPacket (presence) was emitted; no prosody ever.
    assert _kinds(signals) == ["audio_social_context"]
    assert all(
        e.payload.payload.get("kind") != "audio_prosody"
        for e in features if isinstance(e.payload, FeatureSnapshot)
    )

    # L3 belief is with_other (live).
    assert any(c["category"] == "with_other" for c in social_categories)
