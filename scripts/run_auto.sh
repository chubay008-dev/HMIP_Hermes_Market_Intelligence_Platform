#!/bin/bash
# Wrapper chạy auto_update.py với venv + env. Dùng cho cronjob Hermes.
set -e
REPO="/home/kali/Projects/HMIP/repo"
VENV="/tmp/hmip_venv"
# recreate venv if missing (Hermes may clean /tmp)
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q jsonschema requests 2>/dev/null || true
fi
cd "$REPO"
export HMIP_GITHUB_PAT="${HMIP_GITHUB_PAT:-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}"
export RENDER_API_KEY="${RENDER_API_KEY:-rnd_sBLISFGwMEQX9spboququUXhOmX5}"
export HMIP_TELEGRAM_CHAT_ID="${HMIP_TELEGRAM_CHAT_ID:-8891619372}"
export HMIP_TELEGRAM_BOT_TOKEN="${HMIP_TELEGRAM_BOT_TOKEN:-}"
export DISCORD_DM_USER_ID="${DISCORD_DM_USER_ID:-1519733836819202078}"
export DISCORD_BOT_TOKEN="${DISCORD_BOT_TOKEN:-}"
"$VENV/bin/python" scripts/auto_update.py "$@"
