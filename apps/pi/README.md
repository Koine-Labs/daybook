# Daybook Pi Satellite

The Pi is a **sensor satellite**, not a second brain: it connects a
`SatelliteLink` to the Mac hub over WebSocket and streams semantic
`SignalPacket`s (eeg bandpower, audio context, visual scenes). The Mac-side
L1-L6 pipeline owns fusion, prediction, decision, Regis rendering, and
persistence. See `apps/AI_PI_CONTRACT.md` for the full contract + env vars.

## Run

```bash
# On the Mac (hub):
cd apps/inference && DAYBOOK_HUB_KEY=<shared-key> python -m runtime.hub

# On the Pi (satellite):
DAYBOOK_HUB_URL=ws://<mac-ip>:8787 DAYBOOK_HUB_KEY=<shared-key> \
    python apps/pi/satellite.py --sensors eeg
```

`--sensors` is comma-separated from `{eeg, audio, vision, watch}`.

## Layout

- `satellite.py` — the entrypoint; thin delegate to `apps/inference/runtime/satellite.py`.
- `daemon.py` — tombstone for the v0 bedside sleep daemon (removed 2026-06-10;
  see git history). `config.py`, `session.py`, `cues/`, `sensors/`, `firmware/`,
  and `tests/` are v0 leftovers kept for parts salvage only.
