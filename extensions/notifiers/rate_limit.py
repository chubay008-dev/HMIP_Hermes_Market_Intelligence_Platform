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

State BỀN VỮNG (PR #9): ngoài cache in-memory (_state), mốc lần gửi cuối
còn ghi vào bảng pi_notify_state (PI DB, scope="scan"). Render free tier
ngủ/restart → cache mất → đọc lại từ DB → cooldown vẫn sống (tránh re-notify
toàn bộ alert mỗi lần restart). Cache in-memory chỉ tránh round-trip DB.

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
_state_db_path: str | None = None


def _set_state_db_path(path: str | None) -> None:
    """Override PI DB path cho state (test)."""
    global _state_db_path
    _state_db_path = path


def _state_path() -> str | None:
    return _state_db_path or os.getenv("HMIP_PI_DB_PATH") or None


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


def _cross_cooldown_secs() -> float:
    """Cửa sổ cooldown cross-hệ (giây). Đọc HMIP_NOTIFY_SKU_COOLDOWN_MIN
    (cùng env với hệ 1 PI collect) để 2 hệ dùng chung cửa sổ → hệ nào gửi
    trước, hệ kia skip. 0 = tắt cross-hệ.

    PR #11: đồng bộ default với notifier.py (120' thay vì 30') — 30' quá
    ngắn, sau 30' 2 hệ gửi lại cho cùng SP → vẫn spam.
    """
    try:
        return float(os.getenv("HMIP_NOTIFY_SKU_COOLDOWN_MIN", "120")) * 60.0
    except ValueError:
        return 120.0 * 60.0


def reset() -> None:
    """Xoá state (dùng trong test). Xoá cache in-memory luôn; chỉ xoá bảng
    DB khi đã set state path (tránh tạo file hmip_pi.db rác trong cwd)."""
    _state.clear()
    p = _state_path()
    if not p:
        return
    try:
        from extensions.pi import pi_store
        pi_store.clear_notify_state(path=p)
    except Exception:
        pass


def _load_prev(product_name: str) -> dict | None:
    """Đọc mốc notify cuối cho product_name: cache first, rồi DB (restart)."""
    prev = _state.get(product_name)
    if prev is not None:
        return prev
    try:
        from extensions.pi import pi_store
        rec = pi_store.get_notify_state(product_name, path=_state_path())
        if rec and rec.get("last_sent_at"):
            import datetime as _dt
            try:
                ts = _dt.datetime.fromisoformat(rec["last_sent_at"]).timestamp()
            except (ValueError, TypeError):
                return None
            prev = {
                "ts": ts,
                "price": rec.get("last_price"),
                "decision": rec.get("last_decision"),
            }
            _state[product_name] = prev  # populate cache
            return prev
    except Exception:
        pass
    return None


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

    # Lớp 4 (cross-hệ) — check TRƯỚC `prev is None`: dù hệ 2 chưa từng notify
    # SP này (prev=None), nếu hệ 1 (PI collect) đã notify cho cùng SP gần đây
    # (prod:<name> trong cửa sổ cross) → skip. Chống DOUBLE NOTIFY khi 2 hệ chạy
    # song song (PI collect 6h + scheduler scan 30') cho cùng 1 SP giá đổi.
    # Ngoại lệ: giá đổi đáng kể (≥5%) so với mốc cross → event mới → cho phép.
    cross_window = _cross_cooldown_secs()
    if cross_window > 0:
        try:
            import datetime as _dt

            from extensions.pi import pi_store
            rec = pi_store.get_notify_state(
                f"prod:{product_name}", path=_state_path(),
            )
            if rec and rec.get("last_sent_at"):
                try:
                    ts = _dt.datetime.fromisoformat(
                        str(rec["last_sent_at"])
                    ).timestamp()
                    if (time.time() - ts) < cross_window:
                        # Trong cửa sổ — nhưng giá đổi đáng kể → event mới → cho phép.
                        last_p = rec.get("last_price")
                        if last_p is not None and _price_changed_significantly(
                            last_p, price
                        ):
                            pass  # cho phép đi tiếp xuống layer dưới
                        else:
                            return False
                except (ValueError, TypeError):
                    pass
        except Exception as exc:
            log.debug("Cross-hệ state read fail (non-fatal): %s", exc)

    now = time.time()
    cooldown = _cooldown_secs()
    prev = _load_prev(product_name)

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
    """Ghi nhận đã gửi thành công (gọi sau khi ≥1 kênh gửi OK).

    Ghi cả cache in-memory VÀ DB (bền vững qua restart) cho cả scope riêng
    (scan) lẫn cross-hệ (prod:<name> scope pi-sku) để hệ 1 (PI collect) thấy.
    """
    try:
        p = float(price) if price is not None else None
    except (TypeError, ValueError):
        p = None
    _state[product_name] = {
        "ts": time.time(),
        "price": p,
        "decision": decision,
    }
    try:
        from extensions.pi import pi_store
        pi_store.set_notify_state(
            product_name, pi_store.NOTIFY_SCOPE_SCAN,
            last_price=p, last_decision=decision, path=_state_path(),
        )
        # Cross-hệ: ghi prod:<name> scope pi-sku để notify_alert (hệ 1) skip.
        if _cross_cooldown_secs() > 0:
            pi_store.set_notify_state(
                f"prod:{product_name}", "pi-sku",
                last_price=p, last_decision=decision, path=_state_path(),
            )
    except Exception as exc:
        log.debug("scan notify state persist fail (non-fatal): %s", exc)
