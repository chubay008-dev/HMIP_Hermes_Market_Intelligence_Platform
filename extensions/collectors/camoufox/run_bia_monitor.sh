#!/bin/bash
# run_bia_monitor.sh — quét giá 4 site bia VN bằng Camoufox, lưu SQLite.
# Chạy bởi cron hàng ngày. Không gửi Telegram/Discord (theo yêu cầu user).
cd /home/kali
source /home/kali/camoufox-venv/bin/activate
python /home/kali/bia_monitor.py >> /home/kali/bia_monitor.log 2>&1
echo "$(date '+%Y-%m-%d %H:%M') quét xong" >> /home/kali/bia_monitor.log
