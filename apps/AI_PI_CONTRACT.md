# AI ↔ Pi Daemon Contract

The interface between the AI brain (`apps/inference/`) and the Raspberry Pi /
ESP32 sensor satellite.

**Last updated: 2026-06-10.** The May 2026 architecture rebuild deleted the old
`apps/inference/realtime.py` and `apps/inference/cue_decision.py` path. Any Pi
code importing those modules is legacy and must be replaced.

## Current Target Contract

The Pi should be a **sensor satellite**, not a second copy of the old brain.

Runtime shape:

- **MacBook** runs the hub: `HubLink` + `NetworkTransport` + `MessageBus` +
  `assemble_pipeline(bus)` + optional `register_speaker(bus)`.
- **Pi** runs the satellite: `SatelliteLink` + `NetworkTransport` + local sensor
  readers that emit Daybook `SignalPacket`s.
- **ESP32 / Arduino / EXG / mic / camera** feed the Pi, which converts raw device
  output into semantic Daybook packets.

The Pi's job is to publish **semantic packets**, not persist DB rows directly and
not make final decisions. The Mac-side L1-L6 pipeline owns fusion, prediction,
decision, Regis rendering, persistence, and learning.

## Entrypoints (shipped 2026-06-10)

Hub (Mac — full L2→L6 arc + TTS, listening for satellites):

```bash
cd apps/inference
DAYBOOK_HUB_KEY=<shared-key> python -m runtime.hub
# or: python -m runtime.hub --host 0.0.0.0 --port 8787 --key <shared-key>
```

Satellite (Pi or any second machine — sensor edge loops over a SatelliteLink):

```bash
DAYBOOK_HUB_URL=ws://<mac-ip>:8787 DAYBOOK_HUB_KEY=<shared-key> \
    python apps/pi/satellite.py --sensors eeg
# or: cd apps/inference && python -m runtime.satellite --sensors eeg,vision,watch
```

| Env var | Used by | Meaning | Default |
|---|---|---|---|
| `DAYBOOK_HUB_HOST` | hub | bind address for the HubLink WebSocket server | `0.0.0.0` |
| `DAYBOOK_HUB_PORT` | hub | bind port | `8787` |
| `DAYBOOK_HUB_KEY` | both | shared `X-API-Key`; hub fails closed without it | required |
| `DAYBOOK_HUB_URL` | satellite | hub WebSocket URL | `ws://127.0.0.1:8787` |
| `DAYBOOK_USER_ID` | satellite | user the packets belong to | Aakash |

`--sensors` is comma-separated from `{eeg, audio, vision, watch}`. The audio
lane is the real privacy-gated mic loop (needs the `[voice]` extra); eeg /
vision / watch run their edge stubs' synthetic generators until the real ADC /
camera / HealthKit readers are pointed at hardware (the documented swap in each
stub). `apps/pi/daemon.py` is a tombstone: it prints a removal notice and
exits 1.

## Packet Types To Emit First

Start with one packet path and prove it end-to-end:

| Device | Pi interpretation | Daybook modality / kind |
|---|---|---|
| BioAmp EXG Pill via Arduino/ESP32 | blink / clench / bandpower summary | `gesture` event or `bci` / `eeg_bandpower` |
| USB mic | privacy-gated social/prosody context | `audio` / `audio_social_context`, `audio_prosody` |
| ESP32-CAM or USB camera | semantic scene summary | `vision` / `visual_scene` |

Long-term rule: raw audio, raw pixels, and raw EXG samples should be discarded at
the edge after feature extraction. Daybook receives low-bandwidth meaning:
bandpower, blink/clench, social category, prosody, scene setting, object/person
counts, and signal quality.

## Current Code Seams

- `core.bus.network.HubLink`, `SatelliteLink`, `NetworkTransport`
- `core.bus.bus.MessageBus`
- `runtime.hub.build_hub`, `runtime.satellite.build_satellite_bus` + `SENSOR_LOOPS`
- `sensors.participant.emit`
- `sensors.eeg_adapter.EEGBusSink`
- `sensors.audio_adapter.AudioBusSink`
- `sensors.vision_adapter.VisionBusSink`
- `sensors.watch_adapter.WatchBusSink`

The loopback proof that a satellite packet drives the hub arc (and a directive
rides back) lives in `apps/inference/runtime/test_hub_satellite.py`.

---

## Historical v0 Contract

Removed 2026-06-10; see git history (`git log -- apps/AI_PI_CONTRACT.md`, last
full copy at commit `e9cc228`). It described the pre-rebuild bedside sleep
daemon (RealtimeClassifier + CueDecider + direct DB writes) and must not guide
new Pi work.
