# Daybook Runbook

**What command do I type to use X?** Answers here.

> **REBUILD IN PROGRESS (started 2026-05-27).** Most scenarios below depended on v0 modules that have been scrapped (`apps/chat/`, `apps/inference/realtime.py`, `apps/inference/cue_decision.py`, `apps/daybook.py`, the `audio/` TTS chain, etc.). They are progressively out of date and will be rewritten as rebuild phases land per `docs/REBUILD_PLAN.md`.
>
> **What actually runs tonight:**
>
> ```bash
> # Dream-recall capture (works):
> cd $REPO/apps && source inference/.venv/bin/activate
> python -m recall.capture --text "I dreamed about..."
> python -m recall.capture   # interactive mic recording
>
> # FastAPI bridge (limited — chat + compose routes deleted, others work):
> cd $REPO/apps && source inference/.venv/bin/activate
> cd api && uvicorn app:app --host 0.0.0.0 --port 8000 --reload
>
> # LLM + embeddings smoke tests (unaffected):
> [venv] python -m llm.smoke_test
> [venv] python -m embeddings.smoke_test
> ```

This doc is scenario-driven. Skim the **scenarios** section first, then look up specific services + one-shots below as needed.

> **Working directory** for almost every command: `/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook` (the monorepo root). I'll write that as `$REPO`.
>
> **Python venv** for everything Python: `cd $REPO/apps && source inference/.venv/bin/activate`. After that all `python -m ...` commands work. I'll write that as `[venv]` below.

---

## Scenarios — pick what you want to do

### 1. "I want to chat with Regis from the Mac, fastest" (no phone)

One terminal:
```bash
cd $REPO/apps
source inference/.venv/bin/activate
python -m chat.cli
```
Then type. `/quit` to exit. `/new` for a fresh conversation. `/help` for commands.

### 2. "I want voice chat with Regis from the Mac"

Same as above but:
```bash
[venv] python -m chat.voice_cli
```
ENTER starts/stops a mic recording, Regis replies aloud via Kokoro TTS. `--no-speak` for text-only output.

### 3. "I want to talk to Regis from my iPhone (from anywhere on the internet)"

**Two terminals**, both long-running:

Terminal A — FastAPI bridge:
```bash
cd $REPO/apps
source inference/.venv/bin/activate
cd api && uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Terminal B — Cloudflare Tunnel:
```bash
cd $REPO
bin/cloudflare-tunnel-run.sh
```

Then on the iPhone: open **Daybook** → tap "say something to regis" → real reply. Works on cellular too — not tied to home Wi-Fi.

**Skip Terminal B forever:** `sudo cloudflared service install` once. The tunnel then auto-starts at boot in the background. From then on only Terminal A is needed.

### 4. "I want the full always-on daemon — wake-word listener + scheduled morning/pre-sleep briefs + TTS playback"

One terminal:
```bash
[venv] python -m daybook
```
Long-running. Press **Ctrl-C** to stop.

Variants:
```bash
[venv] python -m daybook --mic-only        # just the wake-phrase listener (say "Regis ...")
[venv] python -m daybook --scheduler-only  # just the daily briefs
[venv] python -m daybook --no-speak        # print replies instead of playing TTS
```

### 5. "I want to log a dream this morning"

Text:
```bash
[venv] python -m recall.capture --text "I dreamed about an old library and my grandfather."
```

Or voice (interactive mic, ENTER to start/stop recording):
```bash
[venv] python -m recall.capture
```

Add `--no-ack` to skip Regis's spoken "Held." acknowledgement.

### 6. "I want to check everything is healthy"

```bash
# 1. Local FastAPI up?
curl -s http://localhost:8000/health
# → {"status":"ok",...}

# 2. Public tunnel up?
curl -s https://daybook.koinelabs.com/
# → {"name":"Daybook API",...}

# 3. Chat path end-to-end?
[venv] python -m chat.smoke_test
```

---

## Long-running services (each needs its own terminal)

### A. FastAPI HTTP bridge

**Does:** Exposes the Python brain (chat, recall, observations, sessions, persona, compose, health) over HTTP. The iOS + Watch apps talk to this.

**Start:**
```bash
cd $REPO/apps
source inference/.venv/bin/activate
cd api && uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

**Stop:** Ctrl-C.

**Verify:** `curl http://localhost:8000/health` → 200.

**Notes:**
- `--host 0.0.0.0` is required so the Cloudflare tunnel (or LAN device) can reach it. Default `127.0.0.1` is Mac-only.
- `--reload` auto-restarts on Python file changes. Don't use in production.
- Logs go to the terminal. To background-log: `... >/tmp/uvicorn.log 2>&1 &`.

### B. Cloudflare Tunnel

**Does:** Makes `https://daybook.koinelabs.com` reach your local `localhost:8000` from anywhere on the internet, with HTTPS for free.

**Start (foreground, easy to stop):**
```bash
cd $REPO
bin/cloudflare-tunnel-run.sh
```

**Start (background, auto-start at boot):**
```bash
sudo cloudflared service install   # one-time
# Verify: sudo launchctl list | grep cloudflared
```

**Stop foreground:** Ctrl-C. **Stop service:** `sudo cloudflared service uninstall`.

**Verify:** `curl https://daybook.koinelabs.com/` → 200.

**Auth:** every request through the tunnel needs the `X-API-Key` header (the iOS app sends it automatically from `Daybook-Local.plist`). Loopback Mac dev bypasses the key.

### C. Daybook always-on daemon

**Does:** Mic listener (wakes on "Regis"), scheduled morning/pre-sleep briefs, REM dreaming, outcome labeling, nightly I-Model clustering. The Mac equivalent of "Regis is here all day."

**Start:**
```bash
[venv] python -m daybook
```

**Stop:** Ctrl-C.

**Tune cadence:** set env vars before starting — e.g. `DAYBOOK_MORNING_HOUR=8 DAYBOOK_MORNING_MIN=0 python -m daybook` for an 8:00 morning brief. Full list in the docstring at the top of `apps/daybook.py`.

### D. iOS / Watch app debugging (Xcode)

**Does:** Build + install + attach debugger to the SwiftUI app on a simulator or device.

**Start:** Open `$REPO/apps/ios/Daybook.xcodeproj` in Xcode. Pick destination (your iPhone or a simulator). Press ▶ (Cmd+R).

For the watch scheme specifically, the scheme post-action auto-launches the companion iOS app on the paired iPhone simulator — running `DaybookWatch Watch App` brings up both.

**Stop:** Cmd+. in Xcode or hit the ◼ button.

---

## One-shot commands (run, return, done)

### Sign in to ChatGPT (one-time per Mac)

```bash
[venv] python -m llm.auth.sign_in
```
Opens browser → log in to ChatGPT → tokens persisted to `~/.daybook/auth.json`. Already done for Aakash. Re-run if you ever sign out or hit auth errors.

### Smoke tests (run after code changes in a module)

```bash
[venv] python -m chat.smoke_test         # chat handler end-to-end
[venv] python -m wisp.smoke_test         # composer
[venv] python -m recall.smoke_test       # dream capture
[venv] python -m llm.smoke_test          # ChatClient.auto() path
[venv] python -m embeddings.smoke_test   # BGE-M3 + pgvector
[venv] python -m api.smoke_test          # FastAPI bridge — boots uvicorn on random port, hits every route
[venv] python -m audio.smoke_test        # TTS synth
[venv] python -m audio_context.smoke_test
[venv] python -m visual_context.smoke_test
[venv] python -m wake_word.smoke_test
[venv] python -m imodels.smoke_test
[venv] python -m interject.smoke_test
[venv] python -m intent.smoke_test
[venv] python -m mood.smoke_test
[venv] python -m gesture.smoke_test
```

### Set / change a daily Regis intent

```bash
[venv] python -m intent.capture --text "today i want to write for two hours before noise."
```

### Log a mood snapshot

```bash
[venv] python -m mood.capture --valence 0.6 --arousal 0.3 --notes "calm, content"
```

### Regenerate the Xcode project after editing project.yml

```bash
cd $REPO/apps/ios && xcodegen generate
```

### Force-rebuild iOS app to a specific simulator

```bash
cd $REPO/apps/ios
xcodebuild -project Daybook.xcodeproj -scheme Daybook \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  -configuration Debug build
```

### Tunnel rotate API key (if a key ever leaks)

```bash
NEW_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
sed -i '' "s/^DAYBOOK_API_KEY=.*/DAYBOOK_API_KEY=$NEW_KEY/" \
  "$REPO/apps/inference/.env.local"
$REPO/bin/cloudflare-tunnel-setup.sh    # rewrites Daybook-Local.plist with the new key
# Restart uvicorn (Ctrl-C + restart), then rebuild iOS app
```

---

## First-time setup (already done for Aakash, kept for posterity)

### Python venv

```bash
cd $REPO/apps/inference
uv venv && source .venv/bin/activate
uv pip install -e .
```

### Cloudflare Tunnel (one-time)

```bash
brew install cloudflared
cloudflared tunnel login                       # opens browser → pick koinelabs.com
$REPO/bin/cloudflare-tunnel-setup.sh           # creates tunnel, routes DNS, writes config
sudo cloudflared service install               # optional: auto-start at boot
```

### Database (Neon Postgres)

Connection string lives in `$REPO/apps/inference/.env.local` as `DATABASE_URL`. Already provisioned. To apply a new migration:
```bash
[venv] python -c "
import psycopg
from db import get_conn
with get_conn() as conn:
    with open('migrations/0009_whatever.sql') as f:
        conn.execute(f.read())
    conn.commit()
"
```

---

## Troubleshooting

### "iPhone Daybook app shows 'couldn't reach mac'"

Check in order:
1. Is uvicorn running? `pgrep -af "uvicorn app:app"`. If not, see scenario 3 above.
2. Is the tunnel up? `curl https://daybook.koinelabs.com/` from any terminal. Should return JSON.
3. Is your `Daybook-Local.plist` populated? `cat $REPO/apps/ios/Daybook/Daybook-Local.plist` — should have the tunnel URL + a non-empty key.
4. If you re-ran the setup script after rebuilding the app, you need to rebuild again to pick up the new plist.

### "Watch app icon visible but won't open"

Stuck zombie launch from a prior debug session. Reset:
```bash
# Find your watch sim UDID
xcrun simctl list devices booted | grep "Apple Watch"
# Then:
xcrun simctl shutdown <udid>
xcrun simctl boot <udid>
```
Re-run the watch scheme from Xcode.

### "Chat returns 401"

Either the API key is missing from `Daybook-Local.plist` or it doesn't match the server's `DAYBOOK_API_KEY`. Run `bin/cloudflare-tunnel-setup.sh` to resynchronize.

### "uvicorn won't start — port 8000 in use"

```bash
pkill -f "uvicorn app:app"
# Then start fresh
```

### "ChatGPT auth expired"

```bash
[venv] python -m llm.auth.sign_in
```

### "I changed Python source but uvicorn isn't reloading"

Make sure you started uvicorn with `--reload`. If yes and it still isn't reloading, check uvicorn's terminal for a syntax error — it won't reload broken files. Fix the file, save again.

---

## Quick reference card — copy-paste-able

```bash
# Daily — talk to Regis from phone (the most common scenario)
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps" && source inference/.venv/bin/activate && cd api && uvicorn app:app --host 0.0.0.0 --port 8000 --reload
# (and in another terminal)
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook" && bin/cloudflare-tunnel-run.sh

# Daily — talk to Regis on the Mac
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps" && source inference/.venv/bin/activate && python -m chat.cli

# Daily — log a dream
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps" && source inference/.venv/bin/activate && python -m recall.capture --text "I dreamed..."

# Full always-on
cd "/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook/apps" && source inference/.venv/bin/activate && python -m daybook
```
