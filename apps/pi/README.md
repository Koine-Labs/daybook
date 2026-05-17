# Daybook Pi Daemon

The bedside service that runs on the Raspberry Pi.

Reads sensor packets from ESP32 modules, runs realtime sleep-stage classification (via `apps/inference/`), and fires wisp cues through the configured cue emitters.

Multi-modal by design: pluggable sensor sources (HR/HRV/respiration from ESP32 + EXG Pill, future CAM, future mic) and pluggable cue emitters (stdout for testing, audio for bone-conduction, haptic for vibration motor).

## How it fits

```
┌────────────────────────────────────┐
│  ESP32 (sensors over USB serial)   │
└───────────────┬────────────────────┘
                │ JSON lines
                ↓
┌────────────────────────────────────┐
│  apps/pi/daemon.py                 │
│  ├─ SensorSource threads → queue   │
│  ├─ DB writer thread (sensor_*)    │
│  ├─ Predictor (30s cadence)        │
│  │   └─ RealtimeClassifier         │
│  │   └─ CueDecider                 │
│  └─ CueEmitter on fire             │
└────────────────────────────────────┘
```

See `apps/AI_PI_CONTRACT.md` for the API contract this daemon builds against.

## Install (on the Pi)

```bash
# Use the inference venv — it has the heavy deps (xgboost, numpy, psycopg)
cd /home/koine-labs/code/daybook/apps/inference
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e .

# Add Pi-specific deps to the same venv
cd ../pi
uv pip install -e .
```

## Configure

The daemon reads `apps/inference/.env.local` for `DATABASE_URL`. Other config is via CLI args or `apps/pi/config.toml` (optional, defaults work for v0).

## Run

### v0 — mock sensors, stdout cues (no hardware required)

```bash
cd apps/pi
python -m daemon --sensors mock --cues stdout --duration-minutes 5
```

You'll see:
- Mock HR readings being generated every ~90 seconds
- Every 30s, the predictor logs P(REM)
- After ~60 min (or sooner with `--mock-fast-forward`), cues start to fire to stdout

### v1 — ESP32 serial + stdout cues

```bash
python -m daemon --sensors esp32:/dev/ttyUSB0 --cues stdout
```

### Future — full bedside stack

```bash
python -m daemon \
    --sensors esp32:/dev/ttyUSB0,esp32_cam:/dev/ttyUSB1 \
    --cues audio,haptic:/dev/ttyUSB0
```

## Systemd (eventual)

`/etc/systemd/system/daybook-pi.service` (template in `deploy/`). Not used in v0.

## Open questions (from contract)

See `apps/AI_PI_CONTRACT.md` § "Open questions for the hardware chat" — sensor transport, NTP, audio device, process model, bedside UI.
