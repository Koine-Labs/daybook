"""Thin adapter: a mac-activity reading -> IntentTaggedReading.

Wraps `capture.mac_sensors.capture_once` (its internal FeatureSnapshot is a
convenience carrier here) and re-tags it as a modality+intent reading (#10).
mac HID activity is background, involuntary -> GESTURE modality, CONTINUOUS intent.
The osascript/ioreg probes in mac_sensors are unchanged.
"""
from __future__ import annotations

from capture.mac_sensors import DEFAULT_USER_ID, capture_once
from core.protocol.enums import Intent, Modality
from sensors.contract import IntentTaggedReading


def capture_mac_reading(user_id: str = DEFAULT_USER_ID) -> IntentTaggedReading:
    """Capture one live mac-activity snapshot and tag it as an IntentTaggedReading."""
    snap = capture_once(user_id=user_id)
    return IntentTaggedReading(
        modality=Modality.GESTURE.value,
        intent=Intent.CONTINUOUS.value,
        kind="mac_activity",
        payload=dict(snap.payload),
        source=snap.source,
        timestamp=snap.timestamp,
        user_id=snap.user_id,
        i_model_id=snap.i_model_id,
    )
