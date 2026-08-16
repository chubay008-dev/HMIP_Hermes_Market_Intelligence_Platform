"""notifier.py — Đẩy alert giá sang kênh ngoài (Discord + Telegram).

Thiết kế:
- Đọc credential từ env (Render Dashboard / .env). Thiếu -> skip gracefully.
- Discord: bot token + channel ID (post qua discord.com/api/v10).
  Hỗ trợ DM trực tiếp tới user qua DISCORD_DM_USER_ID (tự tạo DM channel).
- Telegram: bot token (TELEGRAM_HMIP_MARKET_BOT) + chat_id.
- Chỉ gửi CRITICAL alert (tránh spam). Gọi từ events.detect_and_alert.
- Không sửa core/domains.
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger("hmip.notifier")

_DISCORD_API = "https://discord.com/api/v10"
_DISCORD_MSG = _DISCORD_API + "/channels/{channel_id}/messages"
_DISCORD_DM = _DISCORD_API + "/users/@me/channels"
_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Load .hermes/.env nếu env thiếu (chỉ cho local dev; Render set sẵn env).
def _maybe_load_env():
    """Luôn thử nạp .hermes/.env để bổ sung các key thiếu (Discord/Telegram chat)."""
    for cand in ("/home/kali/.hermes/.env", os.path.expanduser("~/.hermes/.env")):
        if not os.path.exists(cand):
            continue
        try:
            with open(cand, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass
        # Chỉ cần load 1 file tồn tại là đủ
        return


def _discord_configured() -> bool:
    """Discord sẵn sàng khi có bot token VÀ (channel ID HOẶC DM user ID)."""
    has_token = bool(os.getenv("DISCORD_BOT_TOKEN"))
    has_target = bool(os.getenv("DISCORD_HOME_CHANNEL") or os.getenv("DISCORD_DM_USER_ID"))
    return has_token and has_target


# Cache DM channel id để tránh tạo lại mỗi lần gửi (Discord trả cùng id cho 1 cặp).
_dm_channel_cache: str | None = None


def _resolve_discord_channel() -> str | None:
    """Trả channel_id để post. Ưu tiên DISCORD_HOME_CHANNEL; nếu không có,
    tạo DM channel với DISCORD_DM_USER_ID (bot phải share server với user)."""
    global _dm_channel_cache
    direct = os.getenv("DISCORD_HOME_CHANNEL")
    if direct:
        return direct
    if _dm_channel_cache:
        return _dm_channel_cache
    user_id = os.getenv("DISCORD_DM_USER_ID")
    if not user_id:
        return None
    token = os.getenv("DISCORD_BOT_TOKEN")
    try:
        r = requests.post(
            _DISCORD_DM,
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json={"recipient_id": user_id},
            timeout=15,
        )
        if r.status_code in (200, 201):
            _dm_channel_cache = r.json().get("id")
            return _dm_channel_cache
        log.warning("Discord DM create fail HTTP %s: %s", r.status_code, r.text[:200])
    except Exception as exc:
        log.warning("Discord DM create error: %s", exc)
    return None


def _telegram_configured() -> bool:
    return bool(os.getenv("TELEGRAM_HMIP_MARKET_BOT") and os.getenv("TELEGRAM_CHAT_ID"))


def _format(alert: dict) -> str:
    etype = alert.get("event_type", "PRICE")
    pname = alert.get("product_name") or alert.get("sku_id") or "?"
    chan = alert.get("channel_id", "?")
    reg = alert.get("region_id", "?")
    pct = alert.get("change_pct", alert.get("price_change_pct", "?"))
    old = alert.get("old_price", "?")
    new = alert.get("new_price", "?")
    return (
        f"🔔 **HMIP Price Alert** [{etype}]\n"
        f"• Sản phẩm: {pname}\n"
        f"• Kênh: {chan} | Vùng: {reg}\n"
        f"• Giá: {old}₫ → {new}₫ ({pct}%)\n"
        f"• Thời gian: {alert.get('timestamp', '?')}"
    )


def send_discord(message: str) -> bool:
    _maybe_load_env()
    if not _discord_configured():
        log.info("Discord chưa cấu hình (thiếu DISCORD_BOT_TOKEN + target)")
        return False
    token = os.getenv("DISCORD_BOT_TOKEN")
    channel_id = _resolve_discord_channel()
    if not channel_id:
        log.warning("Discord: không lấy được channel_id (DM create fail?)")
        return False
    try:
        r = requests.post(
            _DISCORD_MSG.format(channel_id=channel_id),
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
            },
            json={"content": message, "allowed_mentions": {"parse": []}},
            timeout=15,
        )
        if r.status_code not in (200, 201):
            log.warning("Discord send fail HTTP %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as exc:
        log.warning("Discord send error: %s", exc)
        return False


def send_telegram(message: str) -> bool:
    _maybe_load_env()
    if not _telegram_configured():
        log.info("Telegram chưa cấu hình (thiếu TELEGRAM_HMIP_MARKET_BOT/TELEGRAM_CHAT_ID)")
        return False
    token = os.getenv("TELEGRAM_HMIP_MARKET_BOT")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    try:
        r = requests.post(
            _TELEGRAM_API.format(token=token),
            json={"chat_id": chat, "text": message, "parse_mode": "Markdown"},
            timeout=15,
        )
        if r.status_code != 200:
            log.warning("Telegram send fail HTTP %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as exc:
        log.warning("Telegram send error: %s", exc)
        return False


def notify_alert(alert: dict) -> dict[str, bool]:
    """Gửi 1 alert tới các kênh đã cấu hình. Trả {discord, telegram}."""
    msg = _format(alert)
    return {"discord": send_discord(msg), "telegram": send_telegram(msg)}


def notify_alerts(alerts: list[dict]) -> dict[str, int]:
    """Gửi nhiều alert (chỉ CRITICAL). Trả số lượng gửi thành công."""
    sent = {"discord": 0, "telegram": 0}
    for a in alerts:
        if (a.get("severity") or a.get("alert_level")) != "CRITICAL":
            continue
        res = notify_alert(a)
        sent["discord"] += int(res["discord"])
        sent["telegram"] += int(res["telegram"])
    return sent
