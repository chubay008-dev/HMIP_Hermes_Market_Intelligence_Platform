#!/bin/bash
# Gửi báo cáo Channel Comparison 13 kênh qua Telegram + Discord + Gmail
set -e
REPO="/home/kali/Projects/HMIP/repo"
[ -f "$HOME/.hmip_cron_env.sh" ] && . "$HOME/.hmip_cron_env.sh"
cd "$REPO"
"$HOME/.hermes/.gw-venv/bin/python" "$REPO/scripts/send_channel_report.py"
