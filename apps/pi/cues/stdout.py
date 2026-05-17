from __future__ import annotations

import logging
import sys

from .base import CueEmission, CueEmitter

logger = logging.getLogger(__name__)


class StdoutCueEmitter(CueEmitter):
    """Pretends to speak the cue by printing it. For v0 testing."""

    name = "stdout"

    def emit(self, text: str, cue_kind: str) -> CueEmission:
        msg = f"\n  ✦ REGIS would whisper [{cue_kind}]: {text!r}\n"
        print(msg, file=sys.stderr, flush=True)
        logger.info("emitted cue (kind=%s text=%r)", cue_kind, text)
        return CueEmission(text=text, duration_ms=len(text) * 60)  # rough estimate
