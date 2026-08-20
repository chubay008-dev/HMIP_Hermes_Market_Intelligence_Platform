from __future__ import annotations

from extensions.state.discord_cache import DiscordChannelCache

# Initialize Discord cache
_discord_cache = DiscordChannelCache()

"""notifiers/discord.py — bọc gửi cảnh báo Discord (channel hoặc DM).

Thiết kế:
- Đọc bot token + target từ env:
  - DISCORD_BOT_TOKEN (bắt buộc)
  - DISCORD_HOME_CHANNEL (channel ID) HOẶC DISCORD_DM_USER_ID (user ID → DM)
- Nếu chưa cấu hình, chuyển sang "console notifier" (ghi log).
- DM: bot tự tạo DM channel (POST /users/@me/channels) rồi post message.
  Bot phải share server với user để DM hoạt động.
- allowed_mentions parse:[] để tránh ping @everyone/roles.
"""

import logging
import os

import httpx

log = logging.getLogger("hmip.notify.discord")

_DISCORD_API = "https://discord.com/api/v10"
_DISCORD_MSG = _DISCORD_API + "/channels/{channel_id}/messages"
_DISCORD_DM = _DISCORD_API + "/users/@me/channels"

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
HOME_CHANNEL = os.getenv("DISCORD_HOME_CHANNEL", "")
DM_USER_ID = os.getenv("DISCORD_DM_USER_ID", "")

# Cache DM channel id (Discord trả cùng id cho 1 cặp bot-user).
_discord_cache = DiscordChannelCache()


def is_configured() -> bool:
    return bool(BOT_TOKEN and (HOME_CHANNEL or DM_USER_ID))


def _format(
    decision: str,
    product_name: str,
    price,
    delta_percent,
    base_price,
    pack_size: int = 24,
    unit_ml: int = 330,
) -> str:
    arrow = "▲" if (delta_percent or 0) > 0 else "▼"
    dp = f"{delta_percent:+.2f}%" if delta_percent is not None else "—"
    p = f"{float(price):,.0f}" if price is not None else "—"
    emoji = {
        "ALERT": "🟠",
        "ESCALATE": "🔴",
        "HUMAN_REVIEW": "🟡",
    }.get(decision, "⚪")
    # Quy đổi giá/lon sang các đơn vị khác (lon là đơn vị gốc đã chuẩn hoá):
    # - Thùng: × pack_size (bia VN thường 24 lon/thùng).
    # - Chai: 1 chai cùng dung tích (unit_ml) ≈ 1 lon cùng dung tích → giá/chai = giá/lon.
    p_box = f"{float(price) * pack_size:,.0f}" if price is not None else "—"
    unit_label = f"{unit_ml}ml" if unit_ml else ""
    return (
        f"{emoji} **HMIP — Cảnh báo giá**\n"
        f"**Sản phẩm:** {product_name}\n"
        f"**Giá hiện tại (lon):** {p} VND/lon\n"
        f"**Giá thùng ({pack_size} lon):** {p_box} VND/thùng\n"
        f"**Giá chai ({unit_label}):** {p} VND/chai\n"
        f"**Biến động:** {arrow} {dp}\n"
        f"**Quyết định:** {decision}"
    )


def _resolve_channel() -> str | None:
    """Trả channel_id để post. Ưu tiên HOME_CHANNEL; nếu không, tạo DM."""
    # global _dm_channel_cache
    # Replaced with _discord_cache.get_dm_channel()
    if HOME_CHANNEL:
        return HOME_CHANNEL
    if _discord_cache.get_dm_channel():
        return _discord_cache.get_dm_channel()
    if not DM_USER_ID:
        return None
    try:
        resp = httpx.post(
            _DISCORD_DM,
            headers={"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"},
            json={"recipient_id": DM_USER_ID},
            timeout=15.0,
        )
        if resp.status_code in (200, 201):
            _discord_cache.set_dm_channel(resp.json().get("id"))
            return _discord_cache.get_dm_channel()
        log.warning("Discord DM create fail HTTP %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        log.warning("Discord DM create error: %s", exc)
    return None


def notify(
    decision: str,
    product_name: str,
    price=None,
    delta_percent=None,
    base_price=None,
    pack_size: int = 24,
    unit_ml: int = 330,
) -> bool:
    """Gửi cảnh báo Discord. Trả True nếu gửi thành công hoặc console-fallback.

    pack_size: số lon/thùng (mặc định 24 — thùng bia VN). Dùng quy đổi giá thùng.
    unit_ml: dung tích 1 lon/chai (mặc định 330ml). Dùng hiển thị đơn vị chai.
    """
    message = _format(decision, product_name, price, delta_percent, base_price, pack_size, unit_ml)

    if not is_configured():
        log.info("[notify:discord:console-fallback] %s", message.replace("*", ""))
        return True

    channel_id = _resolve_channel()
    if not channel_id:
        log.warning("Discord: không lấy được channel_id (DM create fail?)")
        return False
    try:
        resp = httpx.post(
            _DISCORD_MSG.format(channel_id=channel_id),
            headers={"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"},
            json={"content": message, "allowed_mentions": {"parse": []}},
            timeout=15.0,
        )
        if resp.status_code not in (200, 201):
            log.warning("Discord send fail HTTP %s: %s", resp.status_code, resp.text[:200])
            return False
        return True
    except httpx.HTTPError as exc:
        log.error("Discord notify failed: %s", exc)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    notify("ESCALATE", "Saigon Special 330ml", 20083.0, 11.57, 18000.0)
