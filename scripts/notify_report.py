# -*- coding: utf-8 -*-
"""notify_report.py — Gửi thông báo Telegram & Discord khi một pipeline hoàn tất.

Đọc từ env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DISCORD_WEBHOOK_URL,
DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID. Thiếu cả hai kênh -> SKIP, không fail.

Dùng trong workflow reconcile sau khi cập nhật prices_real.json.

Chạy:
    python3 scripts/notify_report.py \
        --task "reconcile" \
        --summary "reconcile: 28 SKU cập nhật, 60 conflict, 8 anomaly"
"""
from __future__ import annotations
import argparse
import json
import os
import urllib.request
from datetime import datetime

UA = {"User-Agent": "hmip-notify (https://github.com/chubay008-dev/HMIP_Hermes_Market_Intelligence_Platform)"}


def _post(url: str, data: dict, headers: dict | None = None) -> int:
    h = {"Content-Type": "application/json"}
    h.update(UA)
    h.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def send(task_name: str, summary: str) -> None:
    icon = "✅"
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    msg = (f"{icon} HMIP {task_name} hoàn tất ({now})\n"
           f"{summary}\n"
           f"https://github.com/chubay008-dev/HMIP_Hermes_Market_Intelligence_Platform")
    results = []

    # Telegram
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        try:
            st = _post(f"https://api.telegram.org/bot{tg_token}/sendMessage",
                       {"chat_id": tg_chat, "text": msg})
            results.append(f"Telegram {st}")
        except Exception as e:
            results.append(f"Telegram lỗi: {type(e).__name__}")

    # Discord (webhook ưu tiên, fallback bot token)
    dc_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    dc_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    dc_channel = os.environ.get("DISCORD_CHANNEL_ID", "")
    try:
        if dc_url:
            st = _post(dc_url, {"content": msg, "allowed_mentions": {"parse": []}})
            results.append(f"Discord webhook {st}")
        elif dc_token and dc_channel:
            st = _post(f"https://discord.com/api/v10/channels/{dc_channel}/messages",
                       {"content": msg, "allowed_mentions": {"parse": []}},
                       {"Authorization": f"Bot {dc_token}"})
            results.append(f"Discord bot {st}")
    except Exception as e:
        results.append(f"Discord lỗi: {type(e).__name__}")

    print("; ".join(results) if results else "SKIP: không có kênh thông báo được cấu hình")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--summary", default="")
    a = ap.parse_args()
    send(a.task, a.summary)


if __name__ == "__main__":
    main()
