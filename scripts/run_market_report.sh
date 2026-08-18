#!/bin/bash
# Gửi báo cáo Thị trường Bia VN qua Telegram + Discord + Gmail
set -e
REPO="/home/kali/Projects/HMIP/repo"
[ -f "$HOME/.hmip_cron_env.sh" ] && . "$HOME/.hmip_cron_env.sh"
cd "$REPO"
"$HOME/.hermes/.gw-venv/bin/python" "$REPO/scripts/send_market_report.py"
