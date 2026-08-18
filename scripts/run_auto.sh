#!/bin/bash
# Wrapper chạy auto_update.py với venv + env. Dùng cho cronjob Hermes.
set -e
REPO="/home/kali/Projects/HMIP/repo"
VENV="/tmp/hmip_venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q jsonschema requests 2>/dev/null || true
fi
cd "$REPO"
export HMIP_GITHUB_PAT="${HMIP_GITHUB_PAT:-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}"
export RENDER_API_KEY="${RENDER_API_KEY:-rnd_sBLISFGwMEQX9spboququUXhOmX5}"
# Notify dùng Hermes gateway (hermes send) -> không cần bot token ở đây
export HMIP_TELEGRAM_CHAT_ID="8891619372"
export DISCORD_DM_USER_ID="1533881868678725696"
"$VENV/bin/python" scripts/auto_update.py "$@"
