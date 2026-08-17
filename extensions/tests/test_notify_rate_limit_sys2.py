"""test_notify_rate_limit_sys2.py — test anti-spam cho notify_all (scheduler).

Kiểm tra 3 lớp: min-change, cooldown, no-repeat, + mark_sent chỉ ghi khi
thành công, + reset(), + env override.
"""

from __future__ import annotations

import extensions.notifiers as notify_pkg
from extensions.notifiers import rate_limit


def setup_function():
    rate_limit.reset()


def test_allow_first_alert():
    """Lần đầu cho một sản phẩm luôn được phép (chưa có state)."""
    rate_limit.reset()
    assert rate_limit.allow("Bia A", "ESCALATE", 400000.0, 2000.0) is True


def test_min_pct_filter_skips_small_delta(monkeypatch):
    """|delta| < HMIP_SCAN_NOTIFY_MIN_PCT (mặc định 10) → skip."""
    rate_limit.reset()
    monkeypatch.setenv("HMIP_SCAN_NOTIFY_MIN_PCT", "10")
    # delta 5% < 10 → skip
    assert rate_limit.allow("Bia A", "ALERT", 105.0, 5.0) is False
    # delta 10% == ngưỡng → cho phép
    assert rate_limit.allow("Bia A", "ESCALATE", 110.0, 10.0) is True


def test_min_pct_env_override(monkeypatch):
    """Override ngưỡng qua env."""
    rate_limit.reset()
    monkeypatch.setenv("HMIP_SCAN_NOTIFY_MIN_PCT", "20")
    assert rate_limit.allow("Bia A", "ESCALATE", 115.0, 15.0) is False
    assert rate_limit.allow("Bia A", "ESCALATE", 120.0, 20.0) is True


def test_cooldown_skips_same_product_within_window(monkeypatch):
    """Sau mark_sent, cùng sản phẩm (giá không đổi) bị skip trong cooldown."""
    rate_limit.reset()
    monkeypatch.setenv("HMIP_SCAN_NOTIFY_COOLDOWN_MIN", "360")
    monkeypatch.setenv("HMIP_SCAN_NOTIFY_MIN_PCT", "0")
    assert rate_limit.allow("Bia A", "ESCALATE", 400000.0, 2000.0) is True
    rate_limit.mark_sent("Bia A", "ESCALATE", 400000.0)
    # Cùng giá, cùng decision ngay sau → skip (cooldown + no-repeat)
    assert rate_limit.allow("Bia A", "ESCALATE", 400000.0, 2000.0) is False


def test_cooldown_allows_significant_price_change(monkeypatch):
    """Trong cooldown, nếu giá đổi ≥5% so với last → vẫn cho phép (biến động mới)."""
    rate_limit.reset()
    monkeypatch.setenv("HMIP_SCAN_NOTIFY_COOLDOWN_MIN", "360")
    monkeypatch.setenv("HMIP_SCAN_NOTIFY_MIN_PCT", "0")
    rate_limit.mark_sent("Bia A", "ESCALATE", 400000.0)
    # Giá đổi 50% → đáng báo
    assert rate_limit.allow("Bia A", "ESCALATE", 600000.0, 3000.0) is True


def test_cooldown_disabled_when_zero(monkeypatch):
    """HMIP_SCAN_NOTIFY_COOLDOWN_MIN=0 → tắt cooldown, nhưng no-repeat vẫn hoạt động."""
    rate_limit.reset()
    monkeypatch.setenv("HMIP_SCAN_NOTIFY_COOLDOWN_MIN", "0")
    monkeypatch.setenv("HMIP_SCAN_NOTIFY_MIN_PCT", "0")
    rate_limit.mark_sent("Bia A", "ESCALATE", 400000.0)
    # Cooldown tắt, nhưng cùng decision + giá không đổi → no-repeat skip
    assert rate_limit.allow("Bia A", "ESCALATE", 400000.0, 2000.0) is False
    # Giá đổi → cho phép (no-repeat không chặn vì giá khác)
    assert rate_limit.allow("Bia A", "ESCALATE", 450000.0, 2200.0) is True


def test_different_products_independent(monkeypatch):
    """Cooldown per product — SP A không ảnh hưởng SP B."""
    rate_limit.reset()
    monkeypatch.setenv("HMIP_SCAN_NOTIFY_COOLDOWN_MIN", "360")
    monkeypatch.setenv("HMIP_SCAN_NOTIFY_MIN_PCT", "0")
    rate_limit.mark_sent("Bia A", "ESCALATE", 400000.0)
    assert rate_limit.allow("Bia A", "ESCALATE", 400000.0, 2000.0) is False
    # SP B chưa notify → cho phép
    assert rate_limit.allow("Bia B", "ESCALATE", 400000.0, 2000.0) is True


def test_mark_sent_not_called_on_skip(monkeypatch):
    """notify_all skip không gọi mark_sent → alert sau vẫn thử lại."""
    rate_limit.reset()
    monkeypatch.setenv("HMIP_SCAN_NOTIFY_MIN_PCT", "50")
    monkeypatch.setattr(notify_pkg._telegram, "notify", lambda *a, **k: True)
    monkeypatch.setattr(notify_pkg._discord, "notify", lambda *a, **k: True)
    # delta 10% < 50 → skip, trả cả 2 False
    res = notify_pkg.notify_all("ALERT", "Bia A", 110.0, 10.0, 100.0)
    assert res == {"telegram": False, "discord": False}
    # State rỗng (chưa mark_sent)
    assert "Bia A" not in rate_limit._state


def test_mark_sent_called_on_success(monkeypatch):
    """Khi allow + gửi thành công → mark_sent ghi state."""
    rate_limit.reset()
    monkeypatch.setenv("HMIP_SCAN_NOTIFY_MIN_PCT", "0")
    monkeypatch.setattr(notify_pkg._telegram, "notify", lambda *a, **k: True)
    monkeypatch.setattr(notify_pkg._discord, "notify", lambda *a, **k: True)
    notify_pkg.notify_all("ESCALATE", "Bia A", 400000.0, 2000.0, 18000.0)
    assert "Bia A" in rate_limit._state


def test_no_mark_sent_when_both_fail(monkeypatch):
    """Cả 2 kênh fail → không mark_sent (alert sau thử lại)."""
    rate_limit.reset()
    monkeypatch.setenv("HMIP_SCAN_NOTIFY_MIN_PCT", "0")
    monkeypatch.setattr(notify_pkg._telegram, "notify", lambda *a, **k: False)
    monkeypatch.setattr(notify_pkg._discord, "notify", lambda *a, **k: False)
    notify_pkg.notify_all("ESCALATE", "Bia A", 400000.0, 2000.0, 18000.0)
    assert "Bia A" not in rate_limit._state


def test_cooldown_persists_across_cache_clear(tmp_path):
    """State BỀN VỮNG (PR #9): sau mark_sent, xoá cache in-memory (giả lập
    restart Render) → cooldown vẫn sống (đọc từ DB) → alert cùng giá bị skip.
    """
    rate_limit.reset()
    rate_limit._set_state_db_path(str(tmp_path / "scan_state.db"))
    rate_limit.mark_sent("Bia A", "ESCALATE", 400000.0)
    # Giả lập restart: xoá cache in-memory.
    rate_limit._state.clear()
    # Cùng giá, cùng decision ngay sau → skip (cooldown đọc từ DB).
    assert rate_limit.allow("Bia A", "ESCALATE", 400000.0, 2000.0) is False
    rate_limit._set_state_db_path(None)


def test_cooldown_after_restart_allows_significant_change(tmp_path):
    """Sau 'restart' (cache clear), giá đổi đáng kể → vẫn cho phép notify."""
    rate_limit.reset()
    rate_limit._set_state_db_path(str(tmp_path / "scan_state2.db"))
    rate_limit.mark_sent("Bia A", "ESCALATE", 400000.0)
    rate_limit._state.clear()
    # Giá đổi 50% → đáng báo dù cooldown.
    assert rate_limit.allow("Bia A", "ESCALATE", 600000.0, 3000.0) is True
    rate_limit._set_state_db_path(None)


def test_sys2_message_includes_unit_box_bottle():
    """Message Hệ 2 (scheduler) phải ghi rõ đơn vị lon + giá thùng + giá chai."""
    from extensions.notifiers import telegram, discord

    msg = telegram._format("ESCALATE", "Bia Sài Gòn Special 330ml", 18000.0, 20.0, 15000.0, 24, 330)
    assert "VND/lon" in msg
    # Giá thùng = 18000 * 24 = 432000.
    assert "432,000" in msg
    assert "VND/thùng" in msg
    assert "330ml" in msg
    assert "VND/chai" in msg
    # Discord cũng cùng format.
    dmsg = discord._format("ESCALATE", "Bia Sài Gòn Special 330ml", 18000.0, 20.0, 15000.0, 24, 330)
    assert "VND/lon" in dmsg
    assert "432,000" in dmsg
