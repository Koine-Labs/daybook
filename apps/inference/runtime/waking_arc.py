"""Live waking arc runner — Regis speaks on the Mac (production wiring).

Wires the full L1→L6 reflex arc on one in-process bus, with the live microphone
as the L1 producer:

    bus = MessageBus()
    assemble_pipeline(bus, ...)     # real L3 fusion (+ cold-start calibration #4
                                    #   when a DB is configured), real
                                    #   DefaultPolicy (#13 deterministic warrant),
                                    #   default ComposerRenderer (#8, Regis voice)
    register_speaker(bus)           # real TTS sink (lazy audio.streaming)
    listen_continuous(bus=bus, meta_context=WAKING)  # always-on mic producer

The mic loop (voice.loop.listen_continuous) constructs an AudioBusSink + a
ContinuousProcessor and emits privacy-gated audio_social_context / audio_prosody
/ audio_ambient SignalPackets onto TOPIC_SIGNAL under WAKING. They flow L2→L6
through the assembled arc; a social-context transition that clears the L5
warrant makes Regis remark (voice channel, companion posture — #3/#5/#14).

NOT on the CI path: this needs a real microphone, the [voice] extra (torch/
audio/whisper), and a TTS device — none present in CI. CI runs only
`core sensors features fusion prediction decision output`, so `runtime/` is
never collected. Heavy deps are imported LAZILY (inside listen_continuous /
the default speaker / the composer), so even `import runtime.waking_arc`
succeeds with no DATABASE_URL and no audio stack — verified by the spec's
import-clean check.

Run on the Mac (venv + [voice] extra):
  cd apps/inference && python -m runtime.waking_arc
  # or: DAYBOOK_USER_ID=... python -m runtime.waking_arc
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Flat module layout: make both apps/inference and apps importable (voice.loop
# lives under apps/, the L1–L6 modules under apps/inference/).
INF_DIR = Path(__file__).resolve().parent.parent
APPS_DIR = INF_DIR.parent
for p in (str(INF_DIR), str(APPS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.bus.bus import MessageBus
from core.pipeline import assemble_pipeline
from core.protocol.enums import MetaContext
from fusion.participant import CalibrationReader
from output.speaker import register_speaker
from sensors.contract import DEFAULT_USER_ID


def _calibration_reader() -> CalibrationReader | None:
    """The L3 calibration read seam (#4), DB-gated so the arc stays runnable DB-free.

    Mirrors state/declare.py's seam (arbitration.get_calibration, lazily imported)
    but returns None when no DATABASE_URL is configured — get_calibration is
    crash-safe regardless, yet wiring it without a DB would just stamp every
    estimate with a fallback cold_start, so the honest DB-free arc skips it.
    """
    import db

    if not db.DATABASE_URL:
        return None
    from arbitration import get_calibration

    return get_calibration


def build_waking_arc(bus: MessageBus | None = None) -> MessageBus:
    """Assemble the production default arc + the real TTS sink onto a bus.

    The real DefaultPolicy warrant, the default generative ComposerRenderer, and
    the real (lazy) TTS speaker are used; cold-start calibration (#4) is wired
    into L3 whenever a DATABASE_URL is configured. Pure wiring — no mic attached
    yet, so this is import- and call-clean (no audio touched).
    """
    bus = bus or MessageBus()
    assemble_pipeline(bus, calibration_reader=_calibration_reader())
    register_speaker(bus)         # real TTS sink (audio.streaming imported lazily on first speak)
    return bus


def run(*, user_id: str = DEFAULT_USER_ID) -> None:
    """Build the arc and block in the live mic loop (hardware-dependent).

    The mic + audio stack are imported lazily inside listen_continuous, so this
    function only touches hardware when actually called — never at import time.
    """
    from voice.loop import listen_continuous  # light module import; lazies audio internally

    bus = build_waking_arc()
    print("Waking arc up — Regis is listening (Ctrl-C to stop).", flush=True)
    listen_continuous(bus=bus, user_id=user_id, meta_context=MetaContext.WAKING)


def main() -> None:
    user_id = os.environ.get("DAYBOOK_USER_ID", DEFAULT_USER_ID)
    run(user_id=user_id)


if __name__ == "__main__":
    main()
