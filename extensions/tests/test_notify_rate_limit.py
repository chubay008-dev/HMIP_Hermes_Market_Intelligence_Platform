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

import os

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
    assert notifier._pi_notifier_state.get_notify_state() == {}


def test_notify_alert_respects_custom_min_pct_env(monkeypatch):
    """HMIP_NOTIFY_MIN_PCT=15 → change 8% (mặc định pass) bị skip."""
    monkeypatch.setenv("HMIP_NOTIFY_MIN_PCT", "15")
    monkeypatch.setattr(notifier, "send_discord", lambda m: True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: True)

    res = notifier.notify_alert(_alert(change_pct=8.0))

    assert res == {"discord": False, "telegram": False}


def test_notify_alert_respects_custom_cooldown_env(monkeypatch):
    """HMIP_NOTIFY_COOLDOWN_MIN=0 + HMIP_NOTIFY_SKU_COOLDOWN_MIN=0 +
    HMIP_NOTIFY_PRODUCT_COOLDOWN_MIN=0 → không cooldown, alert lặp vẫn gửi."""
    monkeypatch.setenv("HMIP_NOTIFY_COOLDOWN_MIN", "0")
    monkeypatch.setenv("HMIP_NOTIFY_SKU_COOLDOWN_MIN", "0")
    monkeypatch.setenv("HMIP_NOTIFY_PRODUCT_COOLDOWN_MIN", "0")
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
    notifier._pi_notifier_state.get_notify_state().clear()
    # Cùng (sku,channel,region) trong cooldown → skip (đọc từ DB).
    second = notifier.notify_alert(_alert(change_pct=12.0))

    assert first == {"discord": True, "telegram": True}
    assert second == {"discord": False, "telegram": False}
    notifier._set_state_db_path(None)


def test_pi_message_includes_unit_and_box_bottle(monkeypatch):
    """Message Hệ 1 (PI) phải ghi rõ đơn vị lon + giá thùng + giá chai."""
    sent: list[str] = []
    notifier.reset_notify_state()
    monkeypatch.setattr(notifier, "_maybe_load_env", lambda: None)
    monkeypatch.setattr(notifier, "send_discord", lambda m: sent.append(m) or True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: sent.append(m) or True)

    alert = _alert(change_pct=10.0)
    alert["old_price"] = 18000.0
    alert["new_price"] = 19800.0
    alert["pack_size"] = 24
    alert["unit_ml"] = 330
    notifier.notify_alert(alert)

    msg = sent[0]
    # Đơn vị lon rõ ràng.
    assert "₫/lon" in msg
    # Giá thùng = 19800 * 24 = 475200.
    assert "475,200" in msg
    assert "₫/thùng" in msg
    # Đơn vị chai (cùng dung tích ≈ lon).
    assert "330ml" in msg
    assert "₫/chai" in msg


def test_per_sku_cooldown_suppresses_multi_channel_spam(monkeypatch):
    """Anti-spam multi-channel: 1 SP đổi giá trên Tiki+Shopee+Lazada cùng lúc
    → chỉ kênh đầu (Tiki) notify; 2 kênh còn lại bị per-sku cooldown skip.

    Giả lập: notify alert Tiki (gửi), rồi alert Shopee + Lazada cùng SKU
    trong cửa sổ per-sku (30') → cả 2 skip.
    """
    monkeypatch.setenv("HMIP_NOTIFY_SKU_COOLDOWN_MIN", "30")
    sent = []
    monkeypatch.setattr(notifier, "send_discord", lambda m: sent.append(m) or True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: sent.append(m) or True)

    r_tiki = notifier.notify_alert(_alert(sku="SKU-X", channel="TIKI", change_pct=10.0))
    r_shopee = notifier.notify_alert(_alert(sku="SKU-X", channel="SHOPEE", change_pct=10.0))
    r_lazada = notifier.notify_alert(_alert(sku="SKU-X", channel="LAZADA", change_pct=10.0))

    assert r_tiki == {"discord": True, "telegram": True}
    assert r_shopee == {"discord": False, "telegram": False}  # per-sku skip
    assert r_lazada == {"discord": False, "telegram": False}  # per-sku skip
    # Chỉ 2 message (1 discord + 1 telegram) cho kênh đầu.
    assert len(sent) == 2


def test_per_sku_cooldown_independent_per_sku(monkeypatch):
    """2 SP khác nhau trên cùng nhiều kênh → mỗi SP notify đúng 1 lần (kênh đầu).
    SKU-A Tiki gửi, SKU-B Tiki gửi; SKU-A Shopee skip, SKU-B Shopee skip
    (per-sku: mỗi SP chỉ 1 notify trong cửa sổ)."""
    monkeypatch.setenv("HMIP_NOTIFY_SKU_COOLDOWN_MIN", "30")
    sent = []
    monkeypatch.setattr(notifier, "send_discord", lambda m: sent.append(m) or True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: sent.append(m) or True)

    r1 = notifier.notify_alert(_alert(sku="SKU-A", channel="TIKI", change_pct=10.0))
    r2 = notifier.notify_alert(_alert(sku="SKU-B", channel="TIKI", change_pct=10.0))
    r3 = notifier.notify_alert(_alert(sku="SKU-A", channel="SHOPEE", change_pct=10.0))
    r4 = notifier.notify_alert(_alert(sku="SKU-B", channel="SHOPEE", change_pct=10.0))

    assert r1 == {"discord": True, "telegram": True}
    assert r2 == {"discord": True, "telegram": True}
    assert r3 == {"discord": False, "telegram": False}  # SKU-A per-sku skip
    assert r4 == {"discord": False, "telegram": False}  # SKU-B per-sku skip
    assert len(sent) == 4  # 2 gửi × 2 kênh (discord+telegram)


def test_per_sku_cooldown_disabled(monkeypatch):
    """HMIP_NOTIFY_SKU_COOLDOWN_MIN=0 + HMIP_NOTIFY_PRODUCT_COOLDOWN_MIN=0
    → tắt per-sku + per-product, multi-channel gửi hết."""
    monkeypatch.setenv("HMIP_NOTIFY_SKU_COOLDOWN_MIN", "0")
    monkeypatch.setenv("HMIP_NOTIFY_PRODUCT_COOLDOWN_MIN", "0")
    monkeypatch.setenv("HMIP_NOTIFY_COOLDOWN_MIN", "0")
    sent = []
    monkeypatch.setattr(notifier, "send_discord", lambda m: sent.append(m) or True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: sent.append(m) or True)

    r1 = notifier.notify_alert(_alert(sku="SKU-X", channel="TIKI", change_pct=10.0))
    r2 = notifier.notify_alert(_alert(sku="SKU-X", channel="SHOPEE", change_pct=10.0))

    assert r1 == {"discord": True, "telegram": True}
    assert r2 == {"discord": True, "telegram": True}
    assert len(sent) == 4


def test_per_sku_cooldown_persists_across_cache_clear(tmp_path, monkeypatch):
    """Per-sku state bền vững: notify Tiki → xoá cache (giả restart) →
    alert Shopee cùng SKU vẫn bị skip (đọc từ DB)."""
    notifier._set_state_db_path(str(tmp_path / "pi_state.db"))
    notifier.reset_notify_state()
    monkeypatch.setenv("HMIP_NOTIFY_SKU_COOLDOWN_MIN", "30")
    monkeypatch.setattr(notifier, "_maybe_load_env", lambda: None)
    sent = []
    monkeypatch.setattr(notifier, "send_discord", lambda m: sent.append(m) or True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: sent.append(m) or True)

    notifier.notify_alert(_alert(sku="SKU-P", channel="TIKI", change_pct=10.0))
    # Giả restart: xoá cache in-memory (DB vẫn còn).
    notifier._pi_notifier_state.get_sku_notify_state().clear()
    notifier._pi_notifier_state.get_notify_state().clear()
    r_shopee = notifier.notify_alert(_alert(sku="SKU-P", channel="SHOPEE", change_pct=10.0))

    assert r_shopee == {"discord": False, "telegram": False}
    assert len(sent) == 2  # chỉ Tiki gửi


def test_shopee_collector_delegates_to_scraperapi(monkeypatch):
    """ShopeeCollector.collect() delegate sang ScraperAPI.collect_html (SHOPEE)
    — không raise NotImplementedError."""
    from extensions.pi.collectors import ShopeeCollector
    from extensions.pi.scraperapi_collector import ScraperAPICollector

    sc = ShopeeCollector()
    # Monkeypatch ScraperAPICollector.collect_html để verify nó được gọi.
    called: list[str] = []
    def fake_collect_html(self, pid, name, chan, ref_vol=330):
        called.append(chan.channel_id)
        from extensions.pi.collectors import PricePoint
        return PricePoint(product_id=pid, sku_id=f"SKU-{pid}",
                          channel_id=chan.channel_id, region_id="ONLINE",
                          regular_price=19500.0, promotion_price=None,
                          pack_quantity=1, unit_volume_ml=330,
                          source="shopee-scraperapi", raw={})
    monkeypatch.setattr(ScraperAPICollector, "collect_html", fake_collect_html)
    os.environ["SCRAPERAPI_KEY"] = "fake-key"
    try:
        pp = sc.collect("P456", "Heineken 330ml")
    finally:
        os.environ.pop("SCRAPERAPI_KEY", None)
    assert pp is not None
    assert pp.channel_id == "SHOPEE"
    assert called == ["SHOPEE"]


def test_lazada_collector_delegates_to_scraperapi(monkeypatch):
    """LazadaCollector.collect() delegate sang ScraperAPI.collect_html (LAZADA)."""
    from extensions.pi.collectors import LazadaCollector
    from extensions.pi.scraperapi_collector import ScraperAPICollector

    lc = LazadaCollector()
    called: list[str] = []
    def fake_collect_html(self, pid, name, chan, ref_vol=330):
        called.append(chan.channel_id)
        from extensions.pi.collectors import PricePoint
        return PricePoint(product_id=pid, sku_id=f"SKU-{pid}",
                          channel_id=chan.channel_id, region_id="ONLINE",
                          regular_price=21000.0, promotion_price=None,
                          pack_quantity=1, unit_volume_ml=330,
                          source="lazada-scraperapi", raw={})
    monkeypatch.setattr(ScraperAPICollector, "collect_html", fake_collect_html)
    os.environ["SCRAPERAPI_KEY"] = "fake-key"
    try:
        pp = lc.collect("P456", "Heineken 330ml")
    finally:
        os.environ.pop("SCRAPERAPI_KEY", None)
    assert pp is not None
    assert pp.channel_id == "LAZADA"
    assert called == ["LAZADA"]


def test_shopee_collector_no_key_falls_back_to_jina(monkeypatch):
    """Không có SCRAPERAPI/ZENROWS key → fallback Jina (không raise)."""
    from extensions.pi.collectors import ShopeeCollector
    from extensions.pi.jina_collector import JinaCollector

    for k in ("SCRAPERAPI_KEY", "ZENROWS_KEY"):
        os.environ.pop(k, None)
    sc = ShopeeCollector()
    # Monkeypatch JinaCollector.collect để verify fallback tới nó.
    monkeypatch.setattr(
        JinaCollector, "collect",
        lambda self, pid, name, ref_vol=330, channel=None: None,
    )
    result = sc.collect("P1", "Heineken 330ml")
    # Jina trả None (không raise) → result None.
    assert result is None


# ---- Tests: per-product cooldown (PR #11) ----

def test_per_product_cooldown_suppresses_multi_channel_region(monkeypatch):
    """Per-product cooldown (PR #11): 1 SP đổi giá trên nhiều kênh+vùng khác
    cùng lúc → chỉ alert đầu gửi, các alert sau (cùng product_name, khác
    channel/region) bị skip trong cửa sổ per-product.

    Trước fix: 18 kênh × 5 vùng = 90 alerts possible (per-channel 6h chỉ
    gộp từng cặp). Sau fix: per-product gộp tất cả thành 1.
    """
    monkeypatch.setenv("HMIP_NOTIFY_PRODUCT_COOLDOWN_MIN", "240")
    monkeypatch.setenv("HMIP_NOTIFY_SKU_COOLDOWN_MIN", "0")
    monkeypatch.setenv("HMIP_NOTIFY_COOLDOWN_MIN", "0")
    sent = []
    monkeypatch.setattr(notifier, "send_discord", lambda m: sent.append(m) or True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: sent.append(m) or True)

    a1 = _alert(sku="SKU-1", channel="TIKI", region="HCMC", change_pct=15.0)
    a1["product_name"] = "Bia Huda 330ml"
    a2 = _alert(sku="SKU-1", channel="SHOPEE", region="HANOI", change_pct=15.0)
    a2["product_name"] = "Bia Huda 330ml"
    a3 = _alert(sku="SKU-1", channel="LAZADA", region="DANANG", change_pct=15.0)
    a3["product_name"] = "Bia Huda 330ml"

    r1 = notifier.notify_alert(a1)
    r2 = notifier.notify_alert(a2)
    r3 = notifier.notify_alert(a3)

    assert r1 == {"discord": True, "telegram": True}
    assert r2 == {"discord": False, "telegram": False}
    assert r3 == {"discord": False, "telegram": False}
    assert len(sent) == 2


def test_per_product_cooldown_allows_different_products(monkeypatch):
    """Per-product cooldown chỉ skip cùng product_name — SP khác vẫn gửi."""
    monkeypatch.setenv("HMIP_NOTIFY_PRODUCT_COOLDOWN_MIN", "240")
    monkeypatch.setenv("HMIP_NOTIFY_SKU_COOLDOWN_MIN", "0")
    monkeypatch.setenv("HMIP_NOTIFY_COOLDOWN_MIN", "0")
    sent = []
    monkeypatch.setattr(notifier, "send_discord", lambda m: sent.append(m) or True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: sent.append(m) or True)

    a1 = _alert(sku="SKU-1", channel="TIKI", change_pct=15.0)
    a1["product_name"] = "Bia Huda 330ml"
    a2 = _alert(sku="SKU-2", channel="TIKI", change_pct=15.0)
    a2["product_name"] = "Bia Larue 330ml"

    r1 = notifier.notify_alert(a1)
    r2 = notifier.notify_alert(a2)

    assert r1 == {"discord": True, "telegram": True}
    assert r2 == {"discord": True, "telegram": True}
    assert len(sent) == 4


def test_per_product_cooldown_disabled(monkeypatch):
    """HMIP_NOTIFY_PRODUCT_COOLDOWN_MIN=0 → tắt per-product, multi-channel gửi hết."""
    monkeypatch.setenv("HMIP_NOTIFY_PRODUCT_COOLDOWN_MIN", "0")
    monkeypatch.setenv("HMIP_NOTIFY_SKU_COOLDOWN_MIN", "0")
    monkeypatch.setenv("HMIP_NOTIFY_COOLDOWN_MIN", "0")
    sent = []
    monkeypatch.setattr(notifier, "send_discord", lambda m: sent.append(m) or True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: sent.append(m) or True)

    a1 = _alert(sku="SKU-1", channel="TIKI", change_pct=15.0)
    a1["product_name"] = "Bia Huda 330ml"
    a2 = _alert(sku="SKU-1", channel="SHOPEE", change_pct=15.0)
    a2["product_name"] = "Bia Huda 330ml"

    r1 = notifier.notify_alert(a1)
    r2 = notifier.notify_alert(a2)

    assert r1 == {"discord": True, "telegram": True}
    assert r2 == {"discord": True, "telegram": True}
    assert len(sent) == 4


def test_min_change_default_is_8_pct(monkeypatch):
    """PR #11: min-change default tăng từ 5→8% (giảm noise 5-8%)."""
    monkeypatch.delenv("HMIP_NOTIFY_MIN_PCT", raising=False)
    monkeypatch.setenv("HMIP_NOTIFY_SKU_COOLDOWN_MIN", "0")
    monkeypatch.setenv("HMIP_NOTIFY_PRODUCT_COOLDOWN_MIN", "0")
    monkeypatch.setenv("HMIP_NOTIFY_COOLDOWN_MIN", "0")
    monkeypatch.setattr(notifier, "send_discord", lambda m: True)
    monkeypatch.setattr(notifier, "send_telegram", lambda m: True)

    r1 = notifier.notify_alert(_alert(change_pct=7.0))
    r2 = notifier.notify_alert(_alert(change_pct=8.0))
    assert r1 == {"discord": False, "telegram": False}
    assert r2 == {"discord": True, "telegram": True}
