# Daybook Runbook

**What command do I type to use X?** Answers here.

> **Post-rebuild note (2026-05-30).** The L1-L6 architecture has landed. Older
> v0 commands that reference `apps/chat`, `apps/inference/realtime.py`,
> `apps/inference/cue_decision.py`, `apps/daybook.py`, iOS/watch apps, or the old
> Pi daemon are historical unless explicitly marked current.

This doc is scenario-driven. Skim the **scenarios** section first, then look up specific services + one-shots below as needed.

> **Working directory** for almost every command: `/Users/main-mac/Desktop/Coding/Projects/Koine Labs/Repo/daybook` (the monorepo root). I'll write that as `$REPO`.
>
> **Python venv** for everything Python: `cd $REPO/apps && source inference/.venv/bin/activate`. After that all `python -m ...` commands work. I'll write that as `[venv]` below.

---

## Scenarios — pick what you want to do

### 1. "I want to verify the current L1-L6 brain"

```bash
cd $REPO/apps/inference
.venv/bin/python -m pytest -q
```

Recent local result: `307 passed`.

### 2. "I want to verify shared TypeScript protocol types"

```bash
cd $REPO
pnpm typecheck
```

### 3. "I want to run the production L1-L6 pipeline smoke"

```bash
cd $REPO/apps/inference
.venv/bin/python -m core.pipeline
```

This exercises real layer wiring with safe/default participants.

### 4. "I want the real waking mic arc"

Hardware-dependent, off CI, and requires the voice extra / audio permissions:

```bash
cd $REPO/apps/inference
.venv/bin/python -m runtime.waking_arc
```

This wires `assemble_pipeline(bus)` + `register_speaker(bus)` + the live
continuous-mic producer. It is the next Mac-side "using it" smoke.

### 5. "I want to replay real biometric sleep data onto the bus"

Requires `DATABASE_URL` and imported sleep sessions:

```bash
cd $REPO/apps/inference
.venv/bin/python -m runtime.biometric_replay
```

This streams stored watch-style biometrics through L1 -> L2 -> L4 REM nowcast.

### 6. "I want to log a dream"

Text:

```bash
cd $REPO/apps
source inference/.venv/bin/activate
python -m recall.capture --text "I dreamed about an old library and my grandfather."
```

Or voice:

```bash
python -m recall.capture
```

### 7. "I want to bring up the FastAPI bridge"

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

Current routes are limited to the surviving API bridge routes: health, recall,
observations, sessions, persona, and state. The old chat/compose app routes are
not the source of truth after the rebuild.

**Skip Terminal B forever:** `sudo cloudflared service install` once. The tunnel then auto-starts at boot in the background. From then on only Terminal A is needed.

### 8. "I want to run the Pi daemon"

Do not use the old Pi daemon as a current integration target. `apps/pi/daemon.py`
still imports deleted v0 modules (`cue_decision`, `realtime`) and fails its
smoke test. The next implementation should rebuild `apps/pi` as a satellite that
publishes Daybook `SignalPacket`s over `NetworkTransport`.

---

## Long-running services (each needs its own terminal)

### A. FastAPI HTTP bridge

**Does:** Exposes the surviving Python bridge routes over HTTP: health, recall,
observations, sessions, persona, and state. Future clients will talk to this
bridge; the deleted v0 iOS/watch clients are not current.

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

**Auth:** every request through the tunnel needs the `X-API-Key` header. Loopback
Mac dev bypasses the key.

### C. Historical: Daybook always-on daemon

This v0 daemon path is deleted/stale after the rebuild. The current waking
runtime is `python -m runtime.waking_arc` from `apps/inference`.

**Start:**
```bash
[venv] python -m daybook
```

**Stop:** Ctrl-C.

Do not use this command until a new daemon is built against the L1-L6 pipeline.

### D. Historical: iOS / Watch app debugging

The v0 iOS/watch apps were deleted during the architecture rebuild. This section
is preserved only as provenance for the future client rebuild.

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
# apps/inference is a flat module layout run via PYTHONPATH (cwd), NOT a built
# package — install its DEPENDENCIES, not the project itself:
uv pip install -r pyproject.toml --extra dev      # lean base: db + ML inference
uv pip install -r pyproject.toml --extra voice     # + voice loop / continuous mic (heavy: torch)
# (the L1–L6 nervous-system core/layers need only the lean base.)
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
