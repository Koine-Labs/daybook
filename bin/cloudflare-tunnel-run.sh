#!/usr/bin/env bash
#
# Start the Daybook Cloudflare Tunnel in the foreground.
# Forwards https://daybook.koinelabs.com → http://localhost:8000
# (per ~/.cloudflared/config.yml written by cloudflare-tunnel-setup.sh)
#
# Stop with Ctrl-C.

set -euo pipefail

TUNNEL_NAME="daybook"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not installed. Run: brew install cloudflared" >&2
  exit 1
fi

if [ ! -f "$HOME/.cloudflared/config.yml" ]; then
  echo "Tunnel not configured yet. Run: bin/cloudflare-tunnel-setup.sh" >&2
  exit 1
fi

echo "Starting tunnel '$TUNNEL_NAME' — Ctrl-C to stop"
exec cloudflared tunnel run "$TUNNEL_NAME"
