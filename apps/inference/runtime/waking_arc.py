"""Live waking arc runner — Regis speaks on the Mac (production wiring).

Wires the full L1→L6 reflex arc on one in-process bus, with the live microphone
as the L1 producer:

    bus = MessageBus()
    assemble_pipeline(bus)          # real L3 fusion, real DefaultPolicy (#13
                                    #   deterministic warrant), default
                                    #   ComposerRenderer (#8, real Regis voice)
    register_speaker(bus)           # real TTS sink (lazy audio.streaming)
    arbiter = register_meta_arbiter(bus)             # (meta, sub) authority (#14)
    listen_continuous(bus=bus, meta_context=arbiter.current_meta_context)

The mic loop (voice.loop.listen_continuous) constructs an AudioBusSink + a
ContinuousProcessor and emits privacy-gated audio_social_context / audio_prosody
/ audio_ambient SignalPackets onto TOPIC_SIGNAL. They flow L2→L6 through the
assembled arc; a social-context transition that clears the L5 warrant makes
Regis remark (voice channel, companion posture — #3/#5/#14).

The meta the signals ride under is ARBITER-SOURCED, not hardcoded (#14): the
MetaContextArbiter subscribes to TOPIC_BELIEF, folds every L3 BeliefState into
its hysteresis state machine, and the sink reads it per-emit through the bound
`current_meta_context` seam. It starts WAKING (fail-safe default) and without
sustained sleep evidence never flips — default behavior is unchanged.

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

from typing import Callable

from core.bus.bus import MessageBus
from core.pipeline import assemble_pipeline
from fusion.meta_arbiter import register as register_meta_arbiter
from output.speaker import register_speaker
from sensors.contract import DEFAULT_USER_ID


def build_waking_arc(bus: MessageBus | None = None) -> MessageBus:
    """Assemble the production default arc + the real TTS sink onto a bus.

    No injection kwargs: the real DefaultPolicy warrant, the default generative
    ComposerRenderer, and the real (lazy) TTS speaker are used. Pure wiring — no
    mic attached yet, so this is import- and call-clean (no audio touched).
    """
    bus = bus or MessageBus()
    assemble_pipeline(bus)        # production default L2→L6 (real DefaultPolicy, ComposerRenderer)
    register_speaker(bus)         # real TTS sink (audio.streaming imported lazily on first speak)
    return bus


def run(*, user_id: str = DEFAULT_USER_ID, listen_fn: Callable[..., None] | None = None) -> None:
    """Build the arc and block in the live mic loop (hardware-dependent).

    The mic + audio stack are imported lazily inside listen_continuous, so this
    function only touches hardware when actually called — never at import time.
    `listen_fn` is the test seam: when injected, voice.loop is never imported.
    """
    if listen_fn is None:
        from voice.loop import listen_continuous as listen_fn  # light import; lazies audio internally

    bus = build_waking_arc()
    arbiter = register_meta_arbiter(bus)
    print("Waking arc up — Regis is listening (Ctrl-C to stop).", flush=True)
    listen_fn(bus=bus, user_id=user_id, meta_context=arbiter.current_meta_context)


def main() -> None:
    user_id = os.environ.get("DAYBOOK_USER_ID", DEFAULT_USER_ID)
    run(user_id=user_id)


if __name__ == "__main__":
    main()
