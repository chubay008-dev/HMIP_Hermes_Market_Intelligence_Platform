"""notifiers — gộp Telegram + Discord.

`notify_all` gửi alert tới cả 2 kênh đã cấu hình. Mỗi kênh tự fallback
console nếu chưa cấu hình (không lỗi, không break flow).
"""

from __future__ import annotations

import logging

from . import discord as _discord
from . import telegram as _telegram

log = logging.getLogger("hmip.notify")


def notify_all(
    decision: str,
    product_name: str,
    price=None,
    delta_percent=None,
    base_price=None,
) -> dict[str, bool]:
    """Gửi alert tới Telegram + Discord. Trả {telegram, discord} thành công."""
    return {
        "telegram": _telegram.notify(decision, product_name, price, delta_percent, base_price),
        "discord": _discord.notify(decision, product_name, price, delta_percent, base_price),
    }


def is_configured() -> bool:
    """True nếu ít nhất 1 kênh (Telegram hoặc Discord) đã cấu hình."""
    return _telegram.is_configured() or _discord.is_configured()