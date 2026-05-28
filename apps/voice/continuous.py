"""Continuous-audio processing: one window -> privacy-gated semantic packets.

Pure orchestration with injectable I/O (identify/prosody/ambient/writers) so it
unit-tests without a mic, DB, or models. listen_continuous() wires the real ones.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np

APPS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APPS_DIR))
sys.path.insert(0, str(APPS_DIR / "inference"))

from audio_context.privacy import PrivacyGate  # noqa: E402

DEFAULT_USER_ID = "61c18d4c-1c20-408a-bd5f-f5f88fd9922f"


class ContinuousProcessor:
    """Applies the privacy gate to one audio window and emits the allowed packets."""

    def __init__(
        self,
        *,
        user_id: str = DEFAULT_USER_ID,
        identify_speakers: Callable[[np.ndarray, int], list[str]],
        prosody_of: Callable[[np.ndarray, int], dict[str, Any]],
        ambient_of: Callable[[np.ndarray, int], list[dict]],
        write_social: Callable[..., Any],
        write_prosody: Callable[..., Any],
        write_ambient: Callable[..., Any],
        buffer_seconds: float = 30.0,
    ) -> None:
        self.user_id = user_id
        self.identify_speakers = identify_speakers
        self.prosody_of = prosody_of
        self.ambient_of = ambient_of
        self.write_social = write_social
        self.write_prosody = write_prosody
        self.write_ambient = write_ambient
        self.gate = PrivacyGate(buffer_seconds=buffer_seconds)

    def process_window(self, audio: np.ndarray, sample_rate: int, *,
                       vad_active: bool, now: datetime) -> None:
        speakers = self.identify_speakers(audio, sample_rate) if vad_active else []
        decision = self.gate.evaluate(speakers=speakers, now=now)

        self.write_social(
            user_id=self.user_id, recorded_at=now,
            speaker=decision.social_context,
            num_speakers=len(set(speakers)),
            vad_active=vad_active,
        )

        if decision.allow_prosody and vad_active:
            self.write_prosody(user_id=self.user_id, recorded_at=now,
                               prosody=self.prosody_of(audio, sample_rate))

        if decision.allow_ambient and not vad_active:
            classes = self.ambient_of(audio, sample_rate)
            if classes:
                self.write_ambient(user_id=self.user_id, recorded_at=now, top_classes=classes)
