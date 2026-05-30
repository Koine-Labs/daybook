"""Tests for the L2 declaration feature extractor."""
from __future__ import annotations

from datetime import datetime, timezone

from core.protocol.enums import Intent, Modality
from core.protocol.payloads import SignalPacket
from features import declaration


def _sig(text: str, *, kind: str = "state_declaration") -> SignalPacket:
    return SignalPacket(
        user_id="u1",
        timestamp=datetime.now(timezone.utc),
        modality=Modality.TEXT.value,
        intent=Intent.EXPLICIT.value,
        kind=kind,
        payload={"text": text, "consent_scope": "self_report_v1"},
        source="self_report",
    )


def test_non_declaration_text_passthrough():
    snap = declaration.extract(_sig("hello there", kind="chat_message"))
    assert snap.payload["extractor"] == "stub_passthrough"
    assert "claims" not in snap.payload.get("features", {})


def test_quickpick_deterministic(monkeypatch):
    monkeypatch.setenv("DAYBOOK_DECLARE_OFFLINE", "1")
    snap = declaration.extract(_sig("I'm exhausted"))
    feats = snap.payload["features"]
    assert feats["classifier"] == "quickpick"
    assert feats["raw_text"] == "I'm exhausted"
    assert {c["axis"] for c in feats["claims"]} == {"fatigue"}
    snap2 = declaration.extract(_sig("I'm exhausted"))
    assert snap2.payload["features"]["claims"] == feats["claims"]


def test_quickpick_wiped_but_wired_yields_fatigue_and_arousal(monkeypatch):
    monkeypatch.setenv("DAYBOOK_DECLARE_OFFLINE", "1")
    snap = declaration.extract(_sig("wiped but wired"))
    axes = {c["axis"] for c in snap.payload["features"]["claims"]}
    assert "fatigue" in axes
    assert "arousal" in axes


def test_llm_path_used_when_online(monkeypatch):
    monkeypatch.delenv("DAYBOOK_DECLARE_OFFLINE", raising=False)

    class _Claim:
        def __init__(self, axis, value, confidence):
            self.axis, self.value, self.confidence = axis, value, confidence

    class _Result:
        claims = [_Claim("fatigue", 0.8, 0.9)]
        note = "tired"

    class _Client:
        backend = "codex"

        def chat_structured(self, *, system, user, schema):
            return _Result()

    monkeypatch.setattr(declaration, "_get_client", lambda: _Client())
    snap = declaration.extract(_sig("I'm beat"))
    feats = snap.payload["features"]
    assert feats["classifier"] == "llm"
    assert feats["claims"][0]["axis"] == "fatigue"
    assert feats["claims"][0]["value"] == 0.8


def test_falls_back_to_quickpick_when_llm_unavailable(monkeypatch):
    monkeypatch.delenv("DAYBOOK_DECLARE_OFFLINE", raising=False)
    monkeypatch.setattr(declaration, "_get_client", lambda: None)
    snap = declaration.extract(_sig("I'm exhausted"))
    assert snap.payload["features"]["classifier"] == "quickpick"


def _llm_with_claims(monkeypatch, claims):
    class _Result:
        note = ""

    _Result.claims = claims

    class _Client:
        backend = "codex"

        def chat_structured(self, *, system, user, schema):
            return _Result()

    monkeypatch.delenv("DAYBOOK_DECLARE_OFFLINE", raising=False)
    monkeypatch.setattr(declaration, "_get_client", lambda: _Client())


class _C:
    def __init__(self, axis, value, confidence):
        self.axis, self.value, self.confidence = axis, value, confidence


def test_llm_out_of_range_scalar_is_clamped(monkeypatch):
    _llm_with_claims(monkeypatch, [_C("arousal", 85, 0.9)])
    snap = declaration.extract(_sig("I'm wired"))
    claims = snap.payload["features"]["claims"]
    assert claims[0]["value"] == 1.0  # 85 clamped into [0,1]


def test_llm_nan_value_is_rejected(monkeypatch):
    _llm_with_claims(monkeypatch, [_C("arousal", float("nan"), 0.9), _C("fatigue", 0.5, 0.8)])
    snap = declaration.extract(_sig("I'm wired"))
    axes = {c["axis"] for c in snap.payload["features"]["claims"]}
    assert "arousal" not in axes  # NaN scalar dropped
    assert "fatigue" in axes


def test_llm_out_of_range_confidence_is_clamped(monkeypatch):
    _llm_with_claims(monkeypatch, [_C("fatigue", 0.5, 3.0)])
    snap = declaration.extract(_sig("I'm beat"))
    assert snap.payload["features"]["claims"][0]["confidence"] == 1.0


def test_categorical_claim_round_trips_via_llm(monkeypatch):
    _llm_with_claims(monkeypatch, [_C("sleepiness", "drowsy", 0.8)])
    snap = declaration.extract(_sig("I'm sleepy"))
    claim = snap.payload["features"]["claims"][0]
    assert claim["axis"] == "sleepiness"
    assert claim["value"] == "drowsy"


def test_categorical_claim_round_trips_via_quickpick(monkeypatch):
    monkeypatch.setenv("DAYBOOK_DECLARE_OFFLINE", "1")
    snap = declaration.extract(_sig("I'm sleepy"))
    claims = {c["axis"]: c["value"] for c in snap.payload["features"]["claims"]}
    assert claims["sleepiness"] == "drowsy"
