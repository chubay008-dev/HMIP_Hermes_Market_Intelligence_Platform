"""notify_daily_report.py — Gửi Daily Intelligence Report (7 section) qua bot TG+Discord.

Best-effort: thiếu cấu hình → SKIP, không fail pipeline.
Mô tả + chi tiết gửi qua env REPORT_DESC (mặc định 'Daily FMCG Intelligence Report').
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

DESC = os.environ.get("REPORT_DESC", "Daily FMCG Intelligence Report")
TEXT = os.environ.get("REPORT_TEXT", "")
now_vn = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M")


def _post(url: str, data: dict, headers: dict | None = None) -> int:
    h = {"Content-Type": "application/json",
         "User-Agent": "HMIP-daily-report-bot/1.0"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def _tg() -> None:
    token, chat = os.environ.get("TELEGRAM_REPORT_BOT_TOKEN"), os.environ.get(
        "TELEGRAM_REPORT_CHAT_ID")
    if not (token and chat):
        print("notify_daily_report: SKIP Telegram (thiếu TELEGRAM_REPORT_BOT_TOKEN/CHAT_ID)")
        return
    msg = (f"📋 {DESC} — {now_vn}\n"
           f"{TEXT}\n")
    code = _post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {"chat_id": chat, "text": msg[:4000], "disable_web_page_preview": True},
    )
    print(f"notify_daily_report: Telegram {code}")


def _discord() -> None:
    bot, channel = os.environ.get("DISCORD_REPORT_BOT_TOKEN"), os.environ.get(
        "DISCORD_REPORT_CHANNEL_ID")
    if not (bot and channel):
        print("notify_daily_report: SKIP Discord (thiếu DISCORD_REPORT_BOT_TOKEN/CHANNEL_ID)")
        return
    code = _post(
        f"https://discord.com/api/v10/channels/{channel}/messages",
        {"content": f"📋 {DESC} — {now_vn}\n{TEXT[:1900]}"},
        {"Authorization": f"Bot {bot}"},
    )
    print(f"notify_daily_report: Discord {code}")


_tg()
_discord()
