"""Production runtime wiring for the nervous-system arc.

These modules assemble + start the live system on real hardware (mic, TTS). They
are intentionally NOT on the CI path (CI runs core/sensors/features/fusion/
prediction/decision/output only) — they need audio hardware and the [voice]
extra. Keep all heavy imports (sounddevice, audio, voice.continuous internals)
LAZY so importing a runtime module never pulls audio/DB into the import graph.
"""
