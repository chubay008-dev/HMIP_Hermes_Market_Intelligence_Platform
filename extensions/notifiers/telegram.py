"""notifiers/telegram.py — bọc gửi cảnh báo Telegram.

Thiết kế:
- Đọc token/userid từ env (HMIP_TELEGRAM_BOT_TOKEN, HMIP_TELEGRAM_CHAT_ID).
  KHÔNG hardcode secret — tuân thủ quy tắc bảo mật.
- Nếu chưa cấu hình, tự động chuyển sang "console notifier" (ghi log
  thay vì gửi) — app vẫn chạy bình thường, chỉ không có push.
- Hàm `notify(decision, product, price, delta)` chuẩn hóa message.

Phần notify KHÔNG sửa kernel; alert handler gốc chỉ trả dict, còn
việc đẩy đi đâu là chuyện của lớp ngoài (scheduler / API).
"""

from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("hmip.notify")

TELEGRAM_BOT_TOKEN = os.getenv("HMIP_TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("HMIP_TELEGRAM_CHAT_ID", "")


def is_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


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
        f"{emoji} *HMIP — Cảnh báo giá*\n"
        f"*Sản phẩm:* {product_name}\n"
        f"*Giá hiện tại (lon):* {p} VND/lon\n"
        f"*Giá thùng ({pack_size} lon):* {p_box} VND/thùng\n"
        f"*Giá chai ({unit_label}):* {p} VND/chai\n"
        f"*Biến động:* {arrow} {dp}\n"
        f"*Quyết định:* {decision}"
    )


def send_text(message: str) -> bool:
    """Gửi text thô (Daily Report Engine). Console-fallback nếu chưa cấu hình."""
    if not is_configured():
        log.info("[notify:console-fallback] %s", message.replace("*", ""))
        return True
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = httpx.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10.0,
        )
        resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        log.error("Telegram send_text failed: %s", exc)
        return False


def notify(
    decision: str,
    product_name: str,
    price=None,
    delta_percent=None,
    base_price=None,
    pack_size: int = 24,
    unit_ml: int = 330,
) -> bool:
    """Gửi cảnh báo. Trả True nếu gửi thành công/thành công-log.

    pack_size: số lon/thùng (mặc định 24 — thùng bia VN). Dùng quy đổi giá thùng.
    unit_ml: dung tích 1 lon/chai (mặc định 330ml). Dùng hiển thị đơn vị chai.

    Nếu chưa cấu hình Telegram, ghi log (không lỗi) và vẫn trả True
    để không làm hỏng luồng scheduler.
    """
    message = _format(decision, product_name, price, delta_percent, base_price, pack_size, unit_ml)
    return send_text(message)


if __name__ == "__main__":
    # test nhanh (console fallback)
    logging.basicConfig(level=logging.INFO)
    notify("ESCALATE", "Saigon Special 330ml", 20083.0, 11.57, 18000.0)
