"""notifiers — gộp Telegram + Discord.

`notify_all` gửi alert tới cả 2 kênh đã cấu hình. Mỗi kênh tự fallback
console nếu chưa cấu hình (không lỗi, không break flow).
"""

from __future__ import annotations

import logging

from . import discord as _discord
from . import rate_limit
from . import telegram as _telegram

log = logging.getLogger("hmip.notify")


def notify_all(
    decision: str,
    product_name: str,
    price=None,
    delta_percent=None,
    base_price=None,
    pack_size: int = 24,
    unit_ml: int = 330,
) -> dict[str, bool]:
    """Gửi alert tới Telegram + Discord. Trả {telegram, discord} thành công.

    Áp anti-spam 3 lớp (rate_limit.allow): min-change (|delta|≥10%) +
    cooldown per sản phẩm (6h) + no-repeat (cùng decision+giá → skip).
    Chỉ gửi khi allow() trả True; nếu skip trả {telegram: False, discord: False}
    mà không đẩy message đi.

    pack_size: số lon/thùng (mặc định 24 — thùng bia VN). Quy đổi giá thùng.
    unit_ml: dung tích 1 lon/chai (mặc định 330ml). Hiển thị đơn vị chai.
    """
    if not rate_limit.allow(product_name, decision, price, delta_percent):
        log.info(
            "notify skip (rate-limit): %s %s price=%s delta=%s%%",
            product_name, decision, price, delta_percent,
        )
        return {"telegram": False, "discord": False}

    result = {
        "telegram": _telegram.notify(decision, product_name, price, delta_percent, base_price, pack_size, unit_ml),
        "discord": _discord.notify(decision, product_name, price, delta_percent, base_price, pack_size, unit_ml),
    }
    # Chỉ ghi nhận state khi ≥1 kênh gửi thành công (fail → alert sau thử lại).
    if result["telegram"] or result["discord"]:
        rate_limit.mark_sent(product_name, decision, price)
    return result


def is_configured() -> bool:
    """True nếu ít nhất 1 kênh (Telegram hoặc Discord) đã cấu hình."""
    return _telegram.is_configured() or _discord.is_configured()