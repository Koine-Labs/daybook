"""Bone-conduction tap event interface.

Hardware detection lives on the Pi side. This module defines the event SCHEMA
that crosses the Pi -> brain boundary, plus a stub poller for local testing.

Tap intent map (single canonical mapping):
    single -> 'acknowledge'
    double -> 'expand'
    long   -> 'silence'
    triple -> 'see'
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .recorder import record_action

TAP_INTENT_MAP: dict[str, str] = {
    "single": "acknowledge",
    "double": "expand",
    "long": "silence",
    "triple": "see",
}


@dataclass
class TapEvent:
    tap_type: str  # 'single' | 'double' | 'long' | 'triple'
    detected_at: datetime
    confidence: float


def handle_tap(
    event: TapEvent,
    *,
    user_id: str,
    triggered_by: str | None = None,
) -> str:
    """Map tap type -> intent, record as user_actions row, return action id."""
    intent = TAP_INTENT_MAP.get(event.tap_type, "unknown")
    context = {
        "tap_type": event.tap_type,
        "detected_at": event.detected_at.isoformat(),
        "confidence": float(event.confidence),
    }
    return record_action(
        user_id=user_id,
        kind="gesture_tap",
        source="headphone_button",
        intent=intent,
        context=context,
        triggered_by=triggered_by,
    )


def simulate_tap(
    tap_type: str,
    user_id: str,
    *,
    confidence: float = 1.0,
    triggered_by: str | None = None,
) -> str:
    """Manually inject a tap for testing. Returns user_actions id."""
    if tap_type not in TAP_INTENT_MAP:
        raise ValueError(
            f"unknown tap_type {tap_type!r}; expected one of {sorted(TAP_INTENT_MAP)}"
        )
    event = TapEvent(
        tap_type=tap_type,
        detected_at=datetime.now(timezone.utc),
        confidence=confidence,
    )
    return handle_tap(event, user_id=user_id, triggered_by=triggered_by)
