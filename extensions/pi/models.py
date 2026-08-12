"""models.py — Canonical data contracts & constants cho HMIP Price Intelligence.

Tuân thủ Spec §41 (Canonical Data Contract) cho PriceObservation, và
§13 (Core Data Model) cho các entity. Đây là dataclass thuần Python —
không phụ thuộc DB — để có thể unit-test độc lập, rồi serialize thành
dict khi gọi API (Spec §40 yêu cầu request/response schema rõ ràng).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any
from datetime import datetime, timezone
from enum import Enum


# ---------------------------------------------------------------------------
# Controlled vocabularies (Spec §24 Alert severity, §22 Event types, §12 Prices)
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Spec §22 event types
EVENT_PRICE_INCREASE = "PRICE_INCREASE"
EVENT_PRICE_DECREASE = "PRICE_DECREASE"
EVENT_PROMO_STARTED = "PROMOTION_STARTED"
EVENT_PROMO_ENDED = "PROMOTION_ENDED"
EVENT_COMPETITOR_UNDERCUT = "COMPETITOR_UNDERCUT"
EVENT_COMPETITOR_INCREASE = "COMPETITOR_PRICE_INCREASE"
EVENT_NEW_SKU = "NEW_SKU"
EVENT_NEW_SELLER = "NEW_SELLER"
EVENT_NEW_CHANNEL = "NEW_CHANNEL"
EVENT_REGIONAL_ANOMALY = "REGIONAL_ANOMALY"
EVENT_VOLATILITY = "PRICE_VOLATILITY"
EVENT_AVAILABILITY = "AVAILABILITY_ANOMALY"


# ---------------------------------------------------------------------------
# Default thresholds (Spec §24). Category-specific override được hỗ trợ.
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS = {
    "low": 3.0,       # < 3%  -> LOW/INFO
    "medium": 5.0,    # 3-5%  -> MEDIUM
    "high": 10.0,     # 5-10% -> HIGH; >10% -> CRITICAL
}

# Significance scoring (Spec §25 noise reduction)
SIGNIFICANCE_NONE = "NONE"
SIGNIFICANCE_LOW = "LOW"
SIGNIFICANCE_MEDIUM = "MEDIUM"
SIGNIFICANCE_HIGH = "HIGH"


# ---------------------------------------------------------------------------
# Catalog dimensions (Spec §7, §9, §10)
# ---------------------------------------------------------------------------

# Channel universe (Spec §19)
CHANNELS = {
    "SHOPEE": ("Shopee", "ecommerce"),
    "LAZADA": ("Lazada", "ecommerce"),
    "TIKI": ("Tiki", "ecommerce"),
    "WINMART": ("WinMart", "modern_trade"),
    "AEON": ("AEON", "modern_trade"),
    "CONVENIENCE": ("Convenience (GS25/CircleK)", "convenience"),
}

# Region universe (Spec §20)
REGIONS = {
    "HCMC": ("Vietnam", "South", "Ho Chi Minh City"),
    "HANOI": ("Vietnam", "North", "Hanoi"),
    "DANANG": ("Vietnam", "Central", "Da Nang"),
    "CANTHO": ("Vietnam", "South", "Can Tho"),
    "HAIPHONG": ("Vietnam", "North", "Hai Phong"),
}

# Market reference price methodology (Spec §14)
METHOD_MEAN = "mean"
METHOD_MEDIAN = "median"
METHOD_WMEDIAN = "weighted_median"
METHOD_WMEAN = "weighted_mean"


# ---------------------------------------------------------------------------
# Dataclasses — canonical contracts
# ---------------------------------------------------------------------------

@dataclass
class Product:
    product_id: str
    brand_id: str
    category_id: str
    product_name: str
    variant: str | None = None
    pack_size: str | None = None
    volume_ml: float | None = None
    unit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SKU:
    sku_id: str
    product_id: str
    barcode: str | None = None
    pack_quantity: float | None = None
    unit_volume_ml: float | None = None
    normalized_unit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PriceObservation:
    observation_id: str
    sku_id: str
    product_id: str
    brand_id: str
    channel_id: str
    seller_id: str
    region_id: str
    observed_at: str
    collected_at: str
    regular_price: float
    effective_price: float
    currency: str = "VND"
    promotion_price: float | None = None
    unit_price: float | None = None
    normalized_price: float | None = None
    availability: str | None = "in_stock"
    source: str | None = None
    source_url: str | None = None
    extraction_method: str | None = None
    confidence: float | None = 0.9
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["metadata"] = self.metadata
        return d


@dataclass
class PriceEvent:
    event_id: str
    sku_id: str
    timestamp: str
    event_type: str
    significance: str
    confidence: float
    channel_id: str | None = None
    region_id: str | None = None
    old_price: float | None = None
    new_price: float | None = None
    change_percent: float | None = None
    dedup_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AIInsight:
    analysis_id: str
    fact: str
    evidence: str
    inference: str
    confidence: float
    recommendation: str
    event_id: str | None = None
    question: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    generated_at: str | None = None
    input_event_ids: list[str] | None = None
    evidence_ids: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
