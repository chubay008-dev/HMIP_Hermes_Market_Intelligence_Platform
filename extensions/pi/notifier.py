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
import time

import requests

log = logging.getLogger("hmip.notifier")

_DISCORD_API = "https://discord.com/api/v10"
_DISCORD_MSG = _DISCORD_API + "/channels/{channel_id}/messages"
_DISCORD_DM = _DISCORD_API + "/users/@me/channels"
_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# --- Rate limiting (chống spam) -------------------------------------------
# Cooldown per (sku|channel|region): sau khi notify 1 alert cho 1 cặp
# sku/kênh/vùng, bỏ qua mọi alert khác cho chính cặp đó trong cooldown
# này. Mặc định 6h (360') — đủ để bắt giá đổi thật sự, không phải noise
# dao động qua lại trong ngày. Override qua env.
# _notify_state[key] = epoch (s) của lần gửi thành công cuối. In-memory:
# reset khi process restart (chấp nhận — scheduler chạy 1 process dài).
_notify_state: dict[str, float] = {}


def _cooldown_seconds() -> float:
    """Số giây giữa 2 lần notify cho cùng (sku,channel,region)."""
    try:
        return float(int(os.getenv("HMIP_NOTIFY_COOLDOWN_MIN", "360"))) * 60.0
    except (TypeError, ValueError):
        return 360.0 * 60.0


def _min_change_pct() -> float:
    """% thay đổi tối thiểu để notify (mặc định 5 — bỏ noise 1-5%)."""
    try:
        return float(os.getenv("HMIP_NOTIFY_MIN_PCT", "5"))
    except (TypeError, ValueError):
        return 5.0


def _notify_key(alert: dict) -> str:
    return "|".join(
        str(alert.get(k, ""))
        for k in ("sku_id", "channel_id", "region_id")
    )


def _is_suppressed_by_cooldown(alert: dict) -> bool:
    """True nếu alert này cho (sku,channel,region) đã được notify gần đây
    (trong cooldown window) → nên bỏ qua để chống spam."""
    key = _notify_key(alert)
    if not key.strip("|"):
        return False
    last = _notify_state.get(key)
    if last is None:
        return False
    return (time.time() - last) < _cooldown_seconds()


def _record_notify_sent(alert: dict) -> None:
    key = _notify_key(alert)
    if key.strip("|"):
        _notify_state[key] = time.time()


def _alert_change_pct(alert: dict) -> float | None:
    pct = alert.get("change_pct", alert.get("price_change_pct"))
    try:
        return abs(float(pct)) if pct is not None else None
    except (TypeError, ValueError):
        return None


def reset_notify_state() -> None:
    """Xoá state cooldown (cho test / chạy lại sạch)."""
    _notify_state.clear()

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
    """Gửi 1 alert tới các kênh đã cấu hình. Trả {discord, telegram}.

    Chống spam (2 lớp, áp dụng tại đây — điểm funnel duy nhất mọi caller
    đi qua, gồm collector + detect_events):
    1. Min-change: bỏ qua alert có |change_pct| < HMIP_NOTIFY_MIN_PCT
       (mặc định 5%) — không notify noise dao động nhỏ 1-5%.
    2. Cooldown: bỏ qua alert cho (sku,channel,region) đã notify trong
       HMIP_NOTIFY_COOLDOWN_MIN (mặc định 6h) gần đây — tránh gửi liên
       tục cùng 1 SP khi giá dao động qua lại.
    Alert bị bỏ qua vẫn trả {discord:False, telegram:False} (không gửi).
    """
    # Lớp 1: min-change filter.
    pct = _alert_change_pct(alert)
    if pct is not None and pct < _min_change_pct():
        log.info("Notify skip (change %.2f%% < min %.2f%%): %s",
                 pct, _min_change_pct(), _notify_key(alert))
        return {"discord": False, "telegram": False}

    # Lớp 2: cooldown filter.
    if _is_suppressed_by_cooldown(alert):
        log.info("Notify skip (cooldown): %s", _notify_key(alert))
        return {"discord": False, "telegram": False}

    msg = _format(alert)
    result = {"discord": send_discord(msg), "telegram": send_telegram(msg)}
    # Chỉ ghi nhận cooldown khi ít nhất 1 kênh gửi thành công — nếu gửi
    # fail (mạng/token), alert sau vẫn được thử lại.
    if result["discord"] or result["telegram"]:
        _record_notify_sent(alert)
    return result


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
