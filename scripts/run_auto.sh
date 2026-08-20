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
# Secrets phải được cung cấp qua môi trường (cron/systemd) — KHÔNG hardcode trong repo.
: "${HMIP_GITHUB_PAT:?Thiếu HMIP_GITHUB_PAT — export trước khi chạy cron}"
: "${RENDER_API_KEY:?Thiếu RENDER_API_KEY — export trước khi chạy cron}"
export HMIP_GITHUB_PAT RENDER_API_KEY
# Notify dùng Hermes gateway (hermes send) -> không cần bot token ở đây
export HMIP_TELEGRAM_CHAT_ID="8891619372"
export DISCORD_DM_USER_ID="1533881868678725696"
"$VENV/bin/python" scripts/auto_update.py "$@"
