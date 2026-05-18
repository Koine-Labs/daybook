"""Gesture detection — silent back-channel from user to Regis.

Captures non-speech inputs (taps, head nods, voice grunts, eye blinks) and
writes them as user_actions rows. The inverse of the interject system:
gestures are user->Regis without speech, auto-interject is Regis->user without
invocation.

Public surface:
  - record_action(...) -> action_id (universal recorder)
  - classify_grunt(audio, sample_rate) -> {kind, confidence} | None
  - TapEvent + handle_tap(...) -> action_id (bone-conduction taps)
  - simulate_tap(tap_type, user_id) -> action_id (test injection)
"""

from .recorder import record_action
from .tap import TapEvent, handle_tap, simulate_tap
from .voice_grunt import classify_grunt

__all__ = [
    "record_action",
    "classify_grunt",
    "TapEvent",
    "handle_tap",
    "simulate_tap",
]
