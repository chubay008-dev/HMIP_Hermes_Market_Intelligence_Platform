"""rate_limit.py — chống spam notify cho hệ thống PRC-001 scheduler.

Hệ thống notify thứ 2 (scheduler scan_once → run_prc_001 → notify_all) gửi
alert cho mọi decision ALERT/ESCALATE/HUMAN_REVIEW mỗi chu kỳ quét (mặc định
30'). Khi giá vẫn lệch (ví dụ mismatch đơn vị thùng/lon sinh variance% lớn),
cùng alert lặp lại mỗi 30' → spam Telegram/Discord.

Module này áp 3 lớp anti-spam tại `allow()` — điểm funnel mà `notify_all`
gọi trước khi đẩy message đi:

1. Min-change: bỏ qua alert có |delta_percent| < ngưỡng (mặc định 10 → chỉ
   ESCALATE đi qua; ALERT 5-10% bị coi noise).
2. Cooldown: sau khi notify 1 alert cho 1 sản phẩm, bỏ qua alert khác cho
   cùng sản phẩm trong N phút (mặc định 6h), TRỪ khi giá thay đổi đáng kể
   (≥5% so với giá lần notify trước) — tức có biến động mới thì vẫn báo.
3. No-repeat: nếu cùng decision + giá không đổi (within 1%) → skip ngay cả
   khi hết cooldown (tránh lặp cùng trạng thái).

State in-memory (`_state`), reset khi process restart. Chỉ ghi nhận khi
notify thực sự diễn ra (gọi `mark_sent` sau khi ≥1 kênh gửi thành công)
→ nếu fail thì alert sau vẫn thử lại.

Env:
    HMIP_SCAN_NOTIFY_COOLDOWN_MIN — phút cooldown (mặc định 360 = 6h; 0 = tắt).
    HMIP_SCAN_NOTIFY_MIN_PCT      — % delta tối thiểu (mặc định 10).
"""

from __future__ import annotations

import logging
import os
import time

log = logging.getLogger("hmip.notify.rate_limit")

# (product_name) -> {"ts": float, "price": float|None, "decision": str}
_state: dict[str, dict] = {}


def _cooldown_secs() -> float:
    try:
        return float(os.getenv("HMIP_SCAN_NOTIFY_COOLDOWN_MIN", "360")) * 60.0
    except ValueError:
        return 360.0 * 60.0


def _min_pct() -> float:
    try:
        return float(os.getenv("HMIP_SCAN_NOTIFY_MIN_PCT", "10"))
    except ValueError:
        return 10.0


def reset() -> None:
    """Xoá state (dùng trong test)."""
    _state.clear()


def _price_changed_significantly(last: float | None, current) -> bool:
    """True nếu current lệch last ≥5% (có biến động mới đáng báo)."""
    if last is None or current is None:
        return True  # chưa có mốc → cho phép
    try:
        c = float(current)
    except (TypeError, ValueError):
        return True
    if last <= 0:
        return True
    return abs(c - last) / last * 100.0 >= 5.0


def allow(product_name: str, decision: str, price=None, delta_percent=None) -> bool:
    """Quyết định có gửi alert này không. Trả True thì mới gửi.

    Side-effect: KHÔNG ghi nhận state ở đây (gửi có thể fail). Gọi
    `mark_sent()` sau khi ≥1 kênh thành công để tránh skip alert tiếp theo
    nếu lần này fail.
    """
    # Lớp 1: min-change theo |delta_percent|.
    if delta_percent is not None:
        try:
            if abs(float(delta_percent)) < _min_pct():
                return False
        except (TypeError, ValueError):
            pass

    now = time.time()
    cooldown = _cooldown_secs()
    prev = _state.get(product_name)

    # Chưa từng notify → cho phép (lần đầu phát hiện).
    if prev is None:
        return True

    # Lớp 2: cooldown — trong cửa sổ cooldown thì skip trừ khi giá đổi đáng kể.
    if cooldown > 0 and (now - prev["ts"]) < cooldown:
        if not _price_changed_significantly(prev.get("price"), price):
            return False

    # Lớp 3: no-repeat — hết cooldown nhưng decision + giá không đổi → skip.
    if prev.get("decision") == decision and not _price_changed_significantly(
        prev.get("price"), price
    ):
        return False

    return True


def mark_sent(product_name: str, decision: str, price=None) -> None:
    """Ghi nhận đã gửi thành công (gọi sau khi ≥1 kênh gửi OK)."""
    try:
        p = float(price) if price is not None else None
    except (TypeError, ValueError):
        p = None
    _state[product_name] = {
        "ts": time.time(),
        "price": p,
        "decision": decision,
    }
