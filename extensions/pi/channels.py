"""channels.py — Registry kênh thu thập giá (Tiki, Shopee, Lazada...).

Mỗi kênh định nghĩa:
- channel_id    : khoá DB (vd "TIKI", "SHOPEE", "LAZADA").
- channel_name  : tên hiển thị.
- strategy      : "api" (gọi API JSON, vd Tiki /api/v2/products) hoặc
                  "html" (scrape trang search + extract_product_price).
- search_url(q) : URL trang search theo từ khoá (dùng cho strategy "html"
                  và cho tier render-JS Firecrawl/ZenRows/Jina).
- api_url(q)    : URL API JSON (chỉ strategy "api"). Trả None cho kênh "html".

Tier chain (Firecrawl/ScraperAPI/ZenRows/Jina) dùng registry này để biết
cào URL nào + parse kết quả ra sao cho từng kênh, thay vì hardcode Tiki.

Env:
  HMIP_CHANNELS  — danh sách kênh bật, comma-separated (mặc định "TIKI").
    VD: HMIP_CHANNELS=tiki,shopee,lazada  → thu 3 kênh cùng lúc.
    Mỗi kênh lưu observation riêng (channel_id khác) → so sánh cross-channel.

Giới hạn thực tế:
- Tiki  : có public API (/api/v2/products) → ScraperAPI parse JSON chính xác.
- Shopee: bot protection mạnh, không có public API dễ gọi → scrape HTML
          search qua tier render-JS (ScraperAPI/ZenRows/Firecrawl) + dùng
          extract_product_price (pack-aware) để parse giá.
- Lazada: Akamai bot protection, tương tự Shopee → strategy "html".
"""

from __future__ import annotations

from urllib.parse import quote as _urlquote


class ChannelConfig:
    """Cấu hình 1 kênh thu thập giá.

    Subclass đặt class attr: channel_id, channel_name, channel_type, strategy
    + override search_url()/api_url().
    """

    channel_id: str = ""
    channel_name: str = ""
    channel_type: str = "ecommerce"
    strategy: str = "html"  # "api" | "html"

    def search_url(self, query: str) -> str:
        raise NotImplementedError

    def api_url(self, query: str, limit: int = 10) -> str | None:
        return None


class TikiChannel(ChannelConfig):
    channel_id = "TIKI"
    channel_name = "Tiki"
    strategy = "api"

    def search_url(self, query: str) -> str:
        return f"https://tiki.vn/search?q={_urlquote(query)}"

    def api_url(self, query: str, limit: int = 10) -> str | None:
        return f"https://tiki.vn/api/v2/products?q={_urlquote(query)}&limit={limit}"


class ShopeeChannel(ChannelConfig):
    channel_id = "SHOPEE"
    channel_name = "Shopee"
    strategy = "html"

    def search_url(self, query: str) -> str:
        # Shopee dùng keyword param; URL phải encode dấu cách thành %20
        # (Shopee không chấp nhận %20 cho keyword nếu trong path, dùng query).
        return f"https://shopee.vn/search?keyword={_urlquote(query)}"

    def api_url(self, query: str, limit: int = 10) -> str | None:
        # Shopee có /api/v4/search/search_items nhưng cần token (anti-bot);
        # không gọi trực tiếp được → dùng strategy "html".
        return None


class LazadaChannel(ChannelConfig):
    channel_id = "LAZADA"
    channel_name = "Lazada"
    strategy = "html"

    def search_url(self, query: str) -> str:
        return f"https://www.lazada.vn/catalog/?q={_urlquote(query)}"

    def api_url(self, query: str, limit: int = 10) -> str | None:
        return None


REGISTRY: dict[str, ChannelConfig] = {
    "TIKI": TikiChannel(),
    "SHOPEE": ShopeeChannel(),
    "LAZADA": LazadaChannel(),
}


def get_channel(channel_id: str) -> ChannelConfig:
    """Trả ChannelConfig cho channel_id (case-insensitive). Raise KeyError nếu không có."""
    key = channel_id.upper()
    if key not in REGISTRY:
        raise KeyError(f"Unknown channel: {channel_id}. Có: {list(REGISTRY)}")
    return REGISTRY[key]


def configured_channels() -> list[ChannelConfig]:
    """Trả danh sách kênh bật qua env HMIP_CHANNELS (mặc định chỉ TIKI).

    VD: HMIP_CHANNELS=tiki,shopee,lazada → 3 kênh.
    """
    import os

    raw = os.getenv("HMIP_CHANNELS", "TIKI")
    ids = [c.strip().upper() for c in raw.split(",") if c.strip()]
    channels: list[ChannelConfig] = []
    for cid in ids:
        if cid in REGISTRY and REGISTRY[cid] not in channels:
            channels.append(REGISTRY[cid])
    if not channels:
        channels = [REGISTRY["TIKI"]]
    return channels
