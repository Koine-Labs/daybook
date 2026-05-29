"""Consent-scope tags stamped on every sensor_readings write.

Each continuous-sensing surface writes the scope the user opted into at write
time, so policy evolution keeps an audit trail (privacy policy #1 —
pause-on-other-voice; see docs/superpowers/specs/2026-05-27-vertical-slice-waking-empath-design.md §5).
The paired `suppressed_for` column is Week-3 privacy-gate territory and is NOT
set here.
"""
from __future__ import annotations

CONSENT_SCOPES: dict[str, str] = {
    "mac": "mac_activity_v1",
    "hk": "apple_health_v1",
    "voice": "mic_continuous_v1",  # Week 3 continuous-mic opt-in
    "eeg": "eeg_continuous_v1",    # BioAmp EXG Pill onboarding — BCI continuous neural stream
    "vision": "camera_continuous_v1",  # continuous semantic vision lane — scene-only, raw pixels discarded (#11)
}
