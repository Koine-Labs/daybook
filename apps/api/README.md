# Daybook HTTP API

FastAPI bridge that exposes Daybook's Python brain (chat, recall, composer,
embeddings, persona, sessions) to native clients — SwiftUI iOS app today,
webapp later.

Single-user prototype. All endpoints act on Aakash's UUID
(`61c18d4c-1c20-408a-bd5f-f5f88fd9922f`) until an auth layer arrives.

## Run

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
source inference/.venv/bin/activate
cd api
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

`--host 0.0.0.0` is required so the iPhone (on the same Wi-Fi) can reach the
Mac. Loopback-only (`127.0.0.1`) works for the iOS simulator but not for an
on-device build.

Base URL: `http://localhost:8000`

Interactive docs: `http://localhost:8000/docs`

## Phone testing

When testing the iOS app on a real device (same Wi-Fi as the Mac):

1. Start uvicorn with `--host 0.0.0.0` as above.
2. Find the Mac's LAN IP:
   ```bash
   ipconfig getifaddr en0
   ```
   (Use `en1` if you're on a USB-C / dock Ethernet adapter.)
3. Edit `apps/ios/Daybook/Info.plist` and set the `DaybookAPIBaseURL` value to
   `http://<that-ip>:8000`, e.g. `http://192.168.1.42:8000`.
4. Build & run on the device from Xcode. The chat overlay will hit the Mac
   over the LAN.

The simulator can leave `DaybookAPIBaseURL` at the default `http://localhost:8000`
since it shares the host's loopback.

## CORS

`http://localhost:*` and `http://127.0.0.1:*` are allowed (regex). Add deployed
client URL schemes to `app.py` when the iOS app ships.

## Endpoints

### Health

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Service banner |
| GET | `/health` | DB / LLM / embeddings / counters |

### Chat

| Method | Path | Purpose |
|---|---|---|
| POST | `/chat/conversations` | Create a new conversation (body: `{title?: string}`) |
| GET | `/chat/conversations` | List recent conversations (`?limit=20`) |
| POST | `/chat/conversations/{id}/messages` | Send a user message → Regis reply (body: `{text}`) |
| GET | `/chat/conversations/{id}/messages` | List messages in a conversation (`?limit=50&before=ISO`) |

### Recall / dreams

| Method | Path | Purpose |
|---|---|---|
| POST | `/recall` | Log a dream from text (body: `{text, ack}`) |
| POST | `/recall/audio` | Log a dream from a WAV upload (multipart: `audio`, `ack`) |
| GET | `/dreams` | List dreams; optional `?q=` for semantic ranking |
| GET | `/dreams/{id}` | Dream detail incl. voice memo URL + themes |

### Sessions

| Method | Path | Purpose |
|---|---|---|
| GET | `/sessions` | List sleep sessions with stage % summary (`?limit=30&days=30`) |
| GET | `/sessions/{id}` | Full session detail + stage timeline (for hypnograms) |
| GET | `/sessions/{id}/state` | `user_state_estimate` rows over time (live monitoring) |

### Observations

| Method | Path | Purpose |
|---|---|---|
| GET | `/observations` | List `regis_observations`; optional `?q=` for semantic ranking |

### Persona

| Method | Path | Purpose |
|---|---|---|
| GET | `/persona` | Current `PERSONA.md` content + mtime |
| PUT | `/persona` | Overwrite `PERSONA.md` (body: `{content}`) |

### Compose

| Method | Path | Purpose |
|---|---|---|
| POST | `/compose` | Direct call to `wisp.composer.compose_utterance` |

## Example curls

```bash
BASE=http://localhost:8000

curl -s $BASE/health | jq .

# Start a conversation
CONV_ID=$(curl -s -X POST $BASE/chat/conversations \
  -H "Content-Type: application/json" \
  -d '{"title":"morning check-in"}' | jq -r .id)

# Send a message and get Regis's reply
curl -s -X POST $BASE/chat/conversations/$CONV_ID/messages \
  -H "Content-Type: application/json" \
  -d '{"text":"hey, slept poorly. any thoughts?"}' | jq .

# Log a dream
curl -s -X POST $BASE/recall \
  -H "Content-Type: application/json" \
  -d '{"text":"I dreamed of an old library where the books all hummed.","ack":true}' | jq .

# Audio recall
curl -s -X POST $BASE/recall/audio \
  -F "audio=@/path/to/dream.wav" \
  -F "ack=true" | jq .

# Search dreams semantically
curl -s "$BASE/dreams?q=family%20home&limit=5" | jq .

# Compose a one-off Regis utterance
curl -s -X POST $BASE/compose \
  -H "Content-Type: application/json" \
  -d '{"moment_kind":"morning_recall_prompt","explicit_context":"User just woke up, no sensor data."}' \
  | jq .
```

## Smoke test

Automated, starts uvicorn on a random port:

```bash
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps"
source inference/.venv/bin/activate
python -m api.smoke_test
```

Manual (against an already-running uvicorn):

```bash
BASE=http://localhost:8000 bash api/smoke.sh
```

## Architecture notes

- The app sets up `sys.path` for `apps/` and `apps/inference/` at the top of
  `app.py` before any route imports. This mirrors the pattern used by
  `apps/chat/_paths.py` and lets `from db import get_conn`,
  `from embeddings import ...`, `from llm import ChatClient`, etc., all work
  unchanged.
- Routes use absolute imports (`from api.routes...`, `from api.deps...`) so the
  module works whether uvicorn loads it as `app:app` (from `apps/api/` cwd) or
  as `api.app:app` (from `apps/` cwd).
- DB pool is the existing `apps/inference/db.py` pool (min=1, max=4). Bump
  `max_size` there before scaling to many concurrent API consumers.
- Embeddings model is lazy-loaded at first call (~30-40s warm-up). To pre-warm,
  hit `/health` once after start — the bool field `embeddings_loaded` reflects
  the lazy cache state.
- LLM auth status comes from `~/.daybook/auth.json` via
  `llm.auth.session.get_sign_in_status()`. Run `python -m llm.auth.sign_in` from
  `apps/` if `/health` shows `llm_signed_in: false`.
