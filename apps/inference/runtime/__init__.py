"""Production runtime wiring for the nervous-system arc.

These modules assemble + start the live system on real hardware (mic, TTS) and
the distributed hub/satellite topology (hub.py / satellite.py over
NetworkTransport; test_hub_satellite.py proves the relay on loopback, DB-free).
The process entrypoints are intentionally NOT on the CI path (CI runs
core/sensors/features/fusion/prediction/decision/output only) — they need audio
hardware, the [voice] extra, or a real port. Keep all heavy imports
(sounddevice, audio, voice.continuous internals) LAZY so importing a runtime
module never pulls audio/DB into the import graph.
"""
