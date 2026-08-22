# -*- coding: utf-8 -*-
"""notify_done.py — Gửi tin nhắn HOÀN TẤT pipeline qua bot Telegram riêng (chỉ stdlib).

Khác với notify_report.py (báo kết quả TG+Discord), script này chỉ gửi 1 tin
xác nhận "đã hoàn tất" với nội dung mô tả các công việc đã chạy, qua bot
Telegram cấu hình bằng env TELEGRAM_DONE_BOT_TOKEN + TELEGRAM_DONE_CHAT_ID.

Nội dung công việc truyền qua env DONE_TASK_DESC (mỗi job một mô tả riêng).
Thiếu cấu hình -> SKIP, không fail pipeline.

Chạy trong workflow (cuối mỗi job, if: always()):
    RUN_STATUS=${{ job.status }} \
    DONE_TASK_DESC="Thu thập đa nguồn → reconcile → commit prices_real.json" \
    TELEGRAM_DONE_BOT_TOKEN=... TELEGRAM_DONE_CHAT_ID=... \
    python3 scripts/notify_done.py
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

TASK_DESC = os.environ.get("DONE_TASK_DESC", "Pipeline HMIP")
STATUS = os.environ.get("RUN_STATUS", "success")
ICON = "✅" if STATUS == "success" else "❌"

now_vn = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M")
msg = (f"{ICON} HOÀN TẤT pipeline {now_vn} (giờ VN)\n"
       f"{TASK_DESC}\n"
       f"Trạng thái: {STATUS}")


def _post(url: str, data: dict, headers: dict | None = None) -> int:
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def main() -> None:
    results = []

    token = os.environ.get("TELEGRAM_DONE_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_DONE_CHAT_ID", "")
    if token and chat:
        st = _post(f"https://api.telegram.org/bot{token}/sendMessage",
                   {"chat_id": chat, "text": msg})
        results.append(f"Telegram {st}")
    else:
        results.append("Telegram SKIP(thiếu env)")

    dc_token = os.environ.get("DISCORD_DONE_BOT_TOKEN", "")
    dc_channel = os.environ.get("DISCORD_DONE_CHANNEL_ID", "")
    if dc_token and dc_channel:
        st = _post(f"https://discord.com/api/v10/channels/{dc_channel}/messages",
                   {"content": msg, "allowed_mentions": {"parse": []}},
                   {"Authorization": f"Bot {dc_token}"})
        results.append(f"Discord {st}")
    else:
        results.append("Discord SKIP(thiếu env)")

    print("done-notify:", "; ".join(results))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"WARN notify_done lỗi: {type(e).__name__}: {e}", file=sys.stderr)
