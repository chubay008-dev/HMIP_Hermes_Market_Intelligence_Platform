"""Test chống spam notify: min-change filter + cooldown per (sku,channel,region).

Trước fix, `store_price_point_if_changed` notify CRITICAL cứng cho mọi thay đổi
>1% (noise threshold), không có rate-limit → Telegram/Discord bị spam liên tục
mỗi cycle quét cho mỗi SP dao động nhỏ.

Sau fix, `notify_alert` (điểm funnel duy nhất) áp 2 lớp:
1. Min-change: |change_pct| < HMIP_NOTIFY_MIN_PCT (mặc định 5) → skip.
2. Cooldown: (sku,channel,region) đã notify trong HMIP_NOTIFY_COOLDOWN_MIN
   (mặc định 360') → skip.
"""

from __future__ import annotations

import pytest

from extensions.pi import notifier


@pytest.fixture(autouse=True)
def _clean_notify_state(monkeypatch):
    """Mỗi test bắt đầu với state cooldown sạch + không load .env."""
    notifier.reset_notify_state()
    monkeypatch.setattr(notifier, "_maybe_load_env", lambda: None)
    yield
    notifier.reset_notify_state()


def _alert(sku="SKU1", change_pct=10.0, channel="TIKI", region="ONLINE"):
    return {
        "event_type": "PRICE_INCREASE", "sku_id": sku,
        "product_name": sku, "channel_id": channel, "region_id": region,
        "old_price": 100.0, "new_price": 110.0, "change_pct": change_pct,
        "severity": "CRITICAL", "timestamp": "2026-08-16T10:00:00Z",
    }


def test_notify_alert_skips_change_below_min_pct(monkeypatch):
    """Change 2% < default min 5% → không gửi (chống noise)."""
    sent = []
    monkeypatch.setattr(notifier, "send_discord", lambda m: sent.append(m) or True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: sent.append(m) or True)

    res = notifier.notify_alert(_alert(change_pct=2.0))

    assert res == {"discord": False, "telegram": False}
    assert sent == []  # không gửi gì


def test_notify_alert_sends_when_change_above_min_pct(monkeypatch):
    sent = []
    monkeypatch.setattr(notifier, "send_discord", lambda m: sent.append(m) or True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: sent.append(m) or True)

    res = notifier.notify_alert(_alert(change_pct=8.0))

    assert res == {"discord": True, "telegram": True}
    assert len(sent) == 2


def test_notify_alert_cooldown_suppresses_repeat_for_same_sku(monkeypatch):
    """Alert đầu gửi; alert thứ 2 cùng (sku,channel,region) trong cooldown
    → bị bỏ qua (chống spam gửi liên tục)."""
    sent = []
    monkeypatch.setattr(notifier, "send_discord", lambda m: sent.append(m) or True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: sent.append(m) or True)

    first = notifier.notify_alert(_alert(change_pct=10.0))
    second = notifier.notify_alert(_alert(change_pct=12.0))  # cùng SKU

    assert first == {"discord": True, "telegram": True}
    assert second == {"discord": False, "telegram": False}
    # Chỉ 2 message (1 discord + 1 telegram) cho lần đầu.
    assert len(sent) == 2


def test_notify_alert_cooldown_independent_per_sku(monkeypatch):
    """2 SKU khác nhau → cả 2 đều được gửi (cooldown per key)."""
    sent = []
    monkeypatch.setattr(notifier, "send_discord", lambda m: sent.append(m) or True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: sent.append(m) or True)

    r1 = notifier.notify_alert(_alert(sku="SKU-A", change_pct=10.0))
    r2 = notifier.notify_alert(_alert(sku="SKU-B", change_pct=10.0))

    assert r1 == {"discord": True, "telegram": True}
    assert r2 == {"discord": True, "telegram": True}
    assert len(sent) == 4


def test_notify_alert_no_record_on_send_failure(monkeypatch):
    """Gửi fail (cả 2 kênh False) → không ghi cooldown, alert sau vẫn thử lại."""
    monkeypatch.setattr(notifier, "send_discord", lambda m: False)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: False)

    first = notifier.notify_alert(_alert(change_pct=10.0))
    # Vì fail → state không ghi → không bị cooldown.
    assert first == {"discord": False, "telegram": False}
    assert notifier._notify_state == {}


def test_notify_alert_respects_custom_min_pct_env(monkeypatch):
    """HMIP_NOTIFY_MIN_PCT=15 → change 8% (mặc định pass) bị skip."""
    monkeypatch.setenv("HMIP_NOTIFY_MIN_PCT", "15")
    monkeypatch.setattr(notifier, "send_discord", lambda m: True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: True)

    res = notifier.notify_alert(_alert(change_pct=8.0))

    assert res == {"discord": False, "telegram": False}


def test_notify_alert_respects_custom_cooldown_env(monkeypatch):
    """HMIP_NOTIFY_COOLDOWN_MIN=0 → không cooldown, alert lặp vẫn gửi."""
    monkeypatch.setenv("HMIP_NOTIFY_COOLDOWN_MIN", "0")
    sent = []
    monkeypatch.setattr(notifier, "send_discord", lambda m: sent.append(m) or True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: sent.append(m) or True)

    r1 = notifier.notify_alert(_alert(change_pct=10.0))
    r2 = notifier.notify_alert(_alert(change_pct=10.0))

    assert r1 == {"discord": True, "telegram": True}
    assert r2 == {"discord": True, "telegram": True}
    assert len(sent) == 4


def test_notify_alert_cooldown_persists_across_cache_clear(tmp_path, monkeypatch):
    """State BỀN VỮNG (PR #9): sau khi notify, xoá cache in-memory (giả lập
    restart Render) → cooldown vẫn sống (đọc từ DB) → alert cùng key bị skip.
    """
    notifier._set_state_db_path(str(tmp_path / "pi_state.db"))
    notifier.reset_notify_state()
    monkeypatch.setattr(notifier, "_maybe_load_env", lambda: None)
    monkeypatch.setattr(notifier, "send_discord", lambda m: True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: True)

    first = notifier.notify_alert(_alert(change_pct=10.0))
    # Giả lập restart: xoá cache in-memory.
    notifier._notify_state.clear()
    # Cùng (sku,channel,region) trong cooldown → skip (đọc từ DB).
    second = notifier.notify_alert(_alert(change_pct=12.0))

    assert first == {"discord": True, "telegram": True}
    assert second == {"discord": False, "telegram": False}
    notifier._set_state_db_path(None)
