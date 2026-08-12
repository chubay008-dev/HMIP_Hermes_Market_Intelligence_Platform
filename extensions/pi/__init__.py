"""extensions.pi — HMIP Price Intelligence module (Spec v2.0, P0–P2).

Tầng mở rộng BÊN NGOÀI core kernel (không sửa core/domains/).
Cung cấp: schema (pi_store), normalization, seed, analytics, event
detection, alert engine, AI analyst và service orchestration.
"""

from extensions.pi.service import (
    ensure_ready, rebuild, overview, trend, index, positioning, competitor,
    channel, region, promotions, price_events, alerts, sku_explorer,
    ai_analyze, ai_ask, get_catalog, full_workspace,
)

__all__ = [
    "ensure_ready", "rebuild", "overview", "trend", "index", "positioning",
    "competitor", "channel", "region", "promotions", "price_events", "alerts",
    "sku_explorer", "ai_analyze", "ai_ask", "get_catalog", "full_workspace",
]
