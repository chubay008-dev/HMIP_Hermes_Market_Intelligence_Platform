#!/bin/bash
# Wrapper deep-scan: chạy auto_update.py --deep (DuckDuckGo, không hermes_tools)
set -e
REPO="/home/kali/Projects/HMIP/repo"
VENV="/tmp/hmip_venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV" 2>/dev/null || true
  "$VENV/bin/pip" install -q requests jsonschema 2>/dev/null || true
fi
cd "$REPO"
# load secrets từ file NGOÀI repo (không bị git track)
[ -f "$HOME/.hmip_cron_env.sh" ] && . "$HOME/.hmip_cron_env.sh"
RENDER_API_KEY="${RENDER_API_KEY:-}"
HMIP_GITHUB_PAT="${HMIP_GITHUB_PAT:-}"
HMIP_TELEGRAM_CHAT_ID="${HMIP_TELEGRAM_CHAT_ID:-8891619372}"
DISCORD_DM_USER_ID="${DISCORD_DM_USER_ID:-1533881868678725696}"
exec "$VENV/bin/python" scripts/auto_update.py --deep
