#!/usr/bin/env bash
#
# Cloudflare Tunnel setup for Daybook.
#
# Idempotent. Creates (or reuses) a named tunnel called "daybook" that maps
# https://daybook.koinelabs.com → http://localhost:8000 (your FastAPI).
# Also writes apps/ios/Daybook/Daybook-Local.plist (gitignored) with the
# tunnel URL + the API key from apps/inference/.env.local so the iOS app
# picks them up on next build.
#
# Prereqs:
#   - cloudflared installed: brew install cloudflared
#   - One-time login (opens browser): cloudflared tunnel login
#   - koinelabs.com must already be on Cloudflare (it is)
#   - DAYBOOK_API_KEY must exist in apps/inference/.env.local
#
# Usage:
#   bin/cloudflare-tunnel-setup.sh
#
# After setup:
#   bin/cloudflare-tunnel-run.sh     # foreground tunnel
#   sudo cloudflared service install # auto-start at boot (optional)

set -euo pipefail

TUNNEL_NAME="daybook"
HOSTNAME="daybook.koinelabs.com"
LOCAL_URL="http://localhost:8000"

# Repo paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/apps/inference/.env.local"
LOCAL_PLIST="$REPO_ROOT/apps/ios/Daybook/Daybook-Local.plist"
CF_CONFIG="$HOME/.cloudflared/config.yml"

say() { printf "→ %s\n" "$*"; }
ok()  { printf "✓ %s\n" "$*"; }
die() { printf "✗ %s\n" "$*" >&2; exit 1; }

# 1. cloudflared installed?
command -v cloudflared >/dev/null 2>&1 \
  || die "cloudflared not installed. Run: brew install cloudflared"
ok "cloudflared installed: $(cloudflared --version | head -1)"

# 2. Logged in? (tunnel list errors out if not)
if ! cloudflared tunnel list >/dev/null 2>&1; then
  die "Not logged in. Run: cloudflared tunnel login → pick koinelabs.com"
fi
ok "Authenticated with Cloudflare"

# 3. Create or reuse tunnel
TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null \
  | awk -v n="$TUNNEL_NAME" '$2==n {print $1; exit}')
if [ -z "$TUNNEL_ID" ]; then
  say "Creating tunnel '$TUNNEL_NAME'..."
  cloudflared tunnel create "$TUNNEL_NAME"
  TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null \
    | awk -v n="$TUNNEL_NAME" '$2==n {print $1; exit}')
  [ -n "$TUNNEL_ID" ] || die "Failed to create tunnel."
  ok "Tunnel created: $TUNNEL_ID"
else
  ok "Tunnel '$TUNNEL_NAME' already exists: $TUNNEL_ID"
fi

# 4. DNS route → hostname
say "Routing $HOSTNAME → $TUNNEL_NAME..."
if cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME" 2>&1 \
    | tee /tmp/cf-route.log | grep -qE "(Added|already exists|is already a)"; then
  ok "DNS routed (or already routed)"
elif grep -q "successfully" /tmp/cf-route.log; then
  ok "DNS routed"
else
  cat /tmp/cf-route.log
  die "DNS routing failed. Check the error above."
fi

# 5. Write ~/.cloudflared/config.yml so `cloudflared tunnel run daybook`
#    knows to forward to localhost:8000
say "Writing $CF_CONFIG..."
mkdir -p "$(dirname "$CF_CONFIG")"
cat > "$CF_CONFIG" <<EOF
tunnel: $TUNNEL_ID
credentials-file: $HOME/.cloudflared/$TUNNEL_ID.json

ingress:
  - hostname: $HOSTNAME
    service: $LOCAL_URL
  - service: http_status:404
EOF
ok "Wrote $CF_CONFIG"

# 6. Read DAYBOOK_API_KEY
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found. Bootstrap that first."
API_KEY=$(grep -E '^DAYBOOK_API_KEY=' "$ENV_FILE" | head -1 | cut -d= -f2-)
[ -n "$API_KEY" ] || die "DAYBOOK_API_KEY missing in $ENV_FILE"
ok "Read DAYBOOK_API_KEY from .env.local"

# 7. Generate Daybook-Local.plist (gitignored) for the iOS app
say "Writing $LOCAL_PLIST (gitignored)..."
cat > "$LOCAL_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>DaybookAPIBaseURL</key>
    <string>https://$HOSTNAME</string>
    <key>DaybookAPIKey</key>
    <string>$API_KEY</string>
</dict>
</plist>
EOF
ok "Wrote $LOCAL_PLIST"

# 8. Print runbook
cat <<EOF

──────────────────────────────────────────────────────────────────────
✅ Tunnel setup complete.

Next steps:

1. Make sure FastAPI is running:

     cd "$REPO_ROOT/apps"
     source inference/.venv/bin/activate
     cd api && uvicorn app:app --host 0.0.0.0 --port 8000 --reload

2. Start the tunnel (foreground):

     bin/cloudflare-tunnel-run.sh

   OR install as a background service:

     sudo cloudflared service install
     # auto-starts at boot, runs in background

3. Verify from any internet-connected device:

     curl https://$HOSTNAME/
     # → {"name":"Daybook API",...}

4. Re-add the Daybook target to Xcode (regenerate project so the new
   Daybook-Local.plist gets bundled):

     cd apps/ios && xcodegen generate

5. Rebuild the iOS app on your phone. It will pick up the tunnel URL
   and API key from Daybook-Local.plist automatically.
──────────────────────────────────────────────────────────────────────
EOF
