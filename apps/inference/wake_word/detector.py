"""Voice wake-word detection via openWakeWord (ONNX).

WakeEvent is an abstract source so a BCI-imagined-speech detector can emit the
same event type later without changing downstream consumers.

Supports both built-in openWakeWord models ("hey_jarvis", "hey_mycroft", etc.)
AND custom-trained .onnx models. Custom models go under:
    apps/inference/wake_word/models/<name>.onnx
and are auto-discovered when you pass `wake_word=<name>`.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_WAKE_WORD = "hey_jarvis"  # placeholder until a custom "Hey Regis" model exists
DEFAULT_THRESHOLD = 0.5
DEFAULT_SAMPLE_RATE = 16000

# Local custom-model directory — drop trained .onnx files here.
CUSTOM_MODELS_DIR = Path(__file__).resolve().parent / "models"


def _resolve_model_path(wake_word: str) -> str:
    """Return the model identifier OR path openWakeWord should load.

    Resolution order:
      1. DAYBOOK_WAKE_WORD_MODEL_PATH env var (absolute path to .onnx) — wins if set
      2. ./models/<wake_word>.onnx — custom local model
      3. wake_word — passed to openWakeWord as a built-in name
    """
    env_path = os.environ.get("DAYBOOK_WAKE_WORD_MODEL_PATH")
    if env_path:
        return env_path
    candidate = CUSTOM_MODELS_DIR / f"{wake_word}.onnx"
    if candidate.exists():
        return str(candidate)
    return wake_word


@dataclass
class WakeEvent:
    detected_at: datetime
    source: str  # 'voice_wake_word' | 'bci_imagined_speech' | 'physical_tap' | 'manual'
    confidence: float
    raw_audio: bytes | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class VoiceWakeWordDetector:
    """openWakeWord wrapper. Lazily loads ONNX model on first call."""

    def __init__(
        self,
        *,
        wake_word: str = DEFAULT_WAKE_WORD,
        threshold: float = DEFAULT_THRESHOLD,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ) -> None:
        self.wake_word = wake_word
        self.threshold = threshold
        self.sample_rate = sample_rate
        self._model = None

    def get_model(self):
        if self._model is None:
            from openwakeword.model import Model as OWWModel

            model_spec = _resolve_model_path(self.wake_word)
            is_custom = model_spec.endswith(".onnx")
            logger.info(
                "loading openWakeWord model %r (onnx) %s",
                self.wake_word,
                "[custom .onnx]" if is_custom else "[built-in]",
            )
            self._model = OWWModel(
                wakeword_models=[model_spec], inference_framework="onnx"
            )
        return self._model

    def reset(self) -> None:
        """Clear any internal openWakeWord state (e.g., after a positive trigger)."""
        if self._model is not None:
            try:
                self._model.reset()
            except Exception:
                logger.debug("openWakeWord reset failed (non-fatal)", exc_info=True)

    def process_audio_chunk(
        self,
        audio: np.ndarray,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ) -> WakeEvent | None:
        """Return WakeEvent if the wake-word fires on this chunk, else None.

        openWakeWord wants 16 kHz int16 mono, ideally in 80 ms (1280-sample)
        multiples. Adapt as needed.
        """
        if audio.size == 0:
            return None
        if sample_rate != 16000:
            logger.warning(
                "wake-word expects 16kHz audio; got %d (skipping chunk)", sample_rate
            )
            return None

        samples = self._to_int16_mono(audio)
        model = self.get_model()
        try:
            scores = model.predict(samples)
        except Exception:
            logger.exception("openWakeWord predict failed")
            return None

        score = float(scores.get(self.wake_word, 0.0))
        if score < self.threshold:
            return None

        return WakeEvent(
            detected_at=datetime.now(timezone.utc),
            source="voice_wake_word",
            confidence=score,
            raw_audio=samples.tobytes(),
            metadata={
                "wake_word": self.wake_word,
                "threshold": self.threshold,
                "sample_rate": sample_rate,
            },
        )

    @staticmethod
    def _to_int16_mono(audio: np.ndarray) -> np.ndarray:
        arr = audio
        if arr.ndim == 2:
            arr = arr.mean(axis=1)
        if arr.dtype == np.int16:
            return arr
        if arr.dtype in (np.float32, np.float64):
            clipped = np.clip(arr, -1.0, 1.0)
            return (clipped * 32767.0).astype(np.int16)
        return arr.astype(np.int16)


__all__ = ["WakeEvent", "VoiceWakeWordDetector", "DEFAULT_WAKE_WORD"]
