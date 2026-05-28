from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from consent import CONSENT_SCOPES


def test_voice_scope_active():
    assert CONSENT_SCOPES["voice"] == "mic_continuous_v1"
    # existing scopes intact
    assert CONSENT_SCOPES["mac"] == "mac_activity_v1"
    assert CONSENT_SCOPES["hk"] == "apple_health_v1"
