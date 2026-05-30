# AI ↔ Pi Daemon Contract

The interface between the AI brain (`apps/inference/`) and the Raspberry Pi /
ESP32 sensor satellite.

**Last updated: 2026-05-30.** The May 2026 architecture rebuild deleted the old
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
- `sensors.participant.emit`
- `sensors.eeg_adapter.EEGBusSink`
- `sensors.audio_adapter.AudioBusSink`
- `sensors.vision_adapter.VisionBusSink`
- `sensors.watch_adapter.WatchBusSink`

`apps/pi/daemon.py` is currently **not** the current integration point. It is a
v0 daemon and fails because it imports deleted modules. The next Pi task is to
replace it with a small satellite runner that creates a network transport and
publishes the packet types above.

---

## Historical v0 Contract Below

The remaining sections are kept for provenance only. They describe the pre-rebuild
bedside sleep daemon and should not be used as the target for new Pi work.

---

## Architecture in one diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                          PI 4 (daybook-pi.local)                     │
│                                                                      │
│   ESP32 (sensors)                                                    │
│     │ serial/HTTP                                                    │
│     ↓                                                                │
│   apps/pi/daemon.py  ←──── imports ───── apps/inference/realtime.py  │
│     │                                    apps/inference/cue_decision.py │
│     │                                    apps/inference/db.py          │
│     │                                                                │
│     ├── writes sensor_readings → Neon Postgres                       │
│     ├── calls RealtimeClassifier.predict_at() every 30s              │
│     ├── feeds prediction to CueDecider.update()                      │
│     └── on CueDecision.fire == True:                                 │
│           - selects wisp utterance (PERSONA.md slot 4–7)             │
│           - synthesizes via TTS (TBD: ElevenLabs/Cartesia/etc)       │
│           - plays via bone-conduction headphones                     │
│           - fires vibration motor on ESP32 as confirmation           │
│           - writes cue_events row to Postgres                        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Sensor packet format (ESP32 → Pi)

The hardware chat owns the ESP32 firmware. For each sensor reading, the ESP32 emits a JSON line over serial or HTTP POST:

```json
{
  "recorded_at": "2026-05-17T23:00:42.123Z",
  "kind": "heart_rate",
  "value": 68.2,
  "source": "esp32_bioamp_pill"
}
```

**Required fields:**
- `recorded_at` — ISO 8601 UTC string with milliseconds
- `kind` — one of: `heart_rate`, `hrv`, `respiratory_rate`, `spo2`, `eeg_alpha`, `eeg_beta`, `eeg_theta`, `motion_x`, `motion_y`, `motion_z`
- `value` — float
- `source` — short identifier of which sensor/module produced this

The first four kinds match what `RealtimeClassifier` understands today. EEG bands + motion are *future* — emit them now if available, but the v0 classifier ignores them. They'll be wired in once we have EEG training data.

---

## DB writes (Pi → Postgres)

Use the same `apps/inference/db.py` helper. For each sensor packet, insert a `sensor_readings` row:

```python
from db import get_conn

with get_conn() as conn, conn.cursor() as cur:
    cur.execute(
        """
        INSERT INTO sensor_readings
            (session_id, user_id, recorded_at, source, kind, payload)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            session_id,            # the active session's UUID
            user_id,               # Aakash's UUID (61c18d4c-...)
            packet["recorded_at"],
            packet["source"],
            packet["kind"],
            json.dumps(payload),   # see payload shapes below
        ),
    )
```

**Payload shapes (per kind):**

| kind | payload JSON |
|---|---|
| `heart_rate` | `{"bpm": 68.2, "unit": "count/min"}` |
| `hrv` | `{"rmssdMs": 36.0, "unit": "ms"}` (field name is `rmssdMs` for historical compat; can hold SDNN or RMSSD — denote in `unit` if ambiguous) |
| `respiratory_rate` | `{"breathsPerMinute": 14.0, "unit": "count/min"}` |
| `spo2` | `{"percent": 97.5, "unit": "%"}` |
| `eeg_alpha` / `eeg_beta` / `eeg_theta` | `{"microvolts": 12.5, "unit": "uV"}` |
| `motion_x` / `motion_y` / `motion_z` | `{"g": 0.04, "unit": "g"}` |

**Important:** unlike the Apple Health import (which left `session_id` NULL), the Pi MUST set `session_id` on every row. This is the data alignment the historical import didn't have, and getting it right from day 1 simplifies all downstream queries.

---

## Session lifecycle

```python
# At bedtime (user taps "Start" on the bedside display):
session_id = create_sleep_session(user_id=AAKASH_UID, started_at=now)

# Initialize realtime brain:
clf = RealtimeClassifier.load()           # loads production_binary_rem.json
clf.start_session(started_at=now)
decider = CueDecider()
decider.start_session(started_at=now, expected_seconds=8 * 3600)

# Main loop (runs all night):
while session_active:
    packet = read_next_sensor_packet()   # from serial/HTTP queue
    write_to_postgres(packet, session_id)
    clf.add_reading(packet["recorded_at"], packet["kind"], packet["value"])

    if time_for_next_epoch_prediction():
        pred = clf.predict_at(now)
        decision = decider.update(pred)
        if decision.fire:
            utterance = pick_utterance(slot=decision.cue_kind, n_cues_so_far=decider.cues_fired)
            audio = tts_synthesize(utterance.text)
            play_audio_via_bone_conduction(audio)
            fire_vibration(esp32, duration_ms=200)
            log_cue_event(session_id, utterance, decision)

# At wake (detected or timer):
update_sleep_session(session_id, ended_at=now)
schedule_morning_recall_prompt(at=now + timedelta(seconds=90))
```

---

## Public Python API (importable from `apps/pi/`)

```python
# Real-time classifier
from inference.realtime import RealtimeClassifier, RealtimePrediction
clf = RealtimeClassifier.load()
clf.start_session(started_at=tz_aware_datetime)
clf.add_reading(recorded_at, kind, value)
pred = clf.predict_at(epoch_start_at)
# pred.rem_probability: float in [0, 1]
# pred.is_rem: bool (at production threshold)
# pred.n_in_window: dict[str, int]
# pred.features: dict[str, float]

# Cue decider
from inference.cue_decision import CueDecider, CueConfig, CueDecision
decider = CueDecider(CueConfig(...))
decider.start_session(started_at=tz_aware_datetime)
decision = decider.update(pred)
# decision.fire: bool
# decision.reason: str (human-readable, log this)
# decision.cue_kind: str | None (e.g., "rem_whisper")
# decision.proba: float | None

# DB connection (already on the Pi after pi-setup)
from db import get_conn
with get_conn() as conn, conn.cursor() as cur:
    cur.execute(...)
```

The Pi daemon imports these directly. Both modules are pure Python with deps already in `apps/inference/pyproject.toml` (xgboost, numpy, psycopg, python-dotenv). On the Pi, install via:

```bash
cd /opt/daybook/apps/inference
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e .
```

---

## TTS layer (Pi-side, not yet built)

The Pi chat owns this. Suggested interface:

```python
# apps/pi/tts.py
class WispVoice:
    def synthesize(self, text: str, voice_id: str = "regis_v1") -> bytes:
        """Return WAV/MP3 audio bytes for the given text."""

    def play(self, audio: bytes) -> None:
        """Play through default audio device (bone-conduction when plugged in)."""
```

Aakash will pick the TTS provider. ElevenLabs / Cartesia / OpenAI Voice / Sesame all have similar APIs.

---

## Cue event logging (Pi → Postgres)

After each fired cue, write a `cue_events` row:

```sql
INSERT INTO cue_events
  (user_id, session_id, delivered_at, cue_content, content_type, target_stage, actual_stage_at_delivery, audio_duration_ms, audio_ref)
VALUES (...);
```

Fields:
- `cue_content` — the actual text Regis spoke (e.g., "You are dreaming.")
- `content_type` — for v1, always `"rem_whisper"`. Future: `"recall_prompt"`, `"intent_set"`, etc.
- `target_stage` — always `"REM"` for v1
- `actual_stage_at_delivery` — pull from the prediction; useful for retroactive analysis
- `audio_duration_ms` — measured at playback time
- `audio_ref` — optional URL/path to saved audio file (R2/S3 future; local file path for v0)

---

## Failure modes the Pi daemon must handle

1. **ESP32 disconnects mid-session.** Sensor stream pauses. Don't crash — keep predicting with the buffer you have until it stales out (>5 min old → predictions return `hr_n=0` and effectively chance-level probability). Reconnect ESP32 and resume.

2. **DB connection drops.** Buffer writes locally (SQLite or JSONL on disk), flush when DB returns. Predictions don't depend on DB writes.

3. **TTS fails.** Skip the cue. Log it. Fire vibration anyway as backup signal.

4. **Model file missing.** Hard fail at daemon start with a clear error: "Run `python -m classifier.train_production` first." Don't attempt to run without a model.

5. **Buffer overflow.** RealtimeClassifier auto-evicts readings older than `context_seconds + 60` (currently 360s). No manual cleanup needed.

---

## Open questions for the hardware chat

These need answers before the daemon can be finalized. Aakash to resolve as Pi work progresses:

1. **Sensor packet transport.** Serial (USB CDC) or WiFi (HTTP/MQTT)? Recommend serial for v0 — simpler, no networking failure modes.
2. **Pi clock sync.** Pi 4 has no RTC; uses NTP. Make sure NTP is enabled before any session starts (timestamps matter for stage alignment).
3. **Audio output device.** Pi's built-in 3.5mm jack vs USB audio vs Bluetooth. Bluetooth has latency issues — recommend wired.
4. **Daemon process model.** systemd service that auto-starts at boot? Or manual `python daemon.py` for v0?
5. **Bedside UI.** Pure 3.5" TFT (touch)? Or also a web page served from the Pi reachable from phone?

The AI side (this directory) is agnostic to all of these. Pick what's easiest.

---

## Version

Contract version: **v0.1** (2026-05-17). Breaking changes bump the major version and require coordinated updates on both sides. Additive changes (new sensor kinds, new fields) bump the minor version.
