"""normalization.py — Price normalization pipeline (Spec §11).

Quy trình (Spec §11):
    Pack → Unit (per can/bottle) → Liter → 100ml → Comparable Price

Mục đích: so sánh được các SKU khác quy cách. Ví dụ Tiger 330ml×24
(368k) vs Heineken 500ml×24 (395k) — so trực tiếp là sai, phải về
giá/100ml.

Các measure hỗ trợ (§11):
    - price per unit (can/bottle)
    - price per liter
    - price per 100ml  (chọn làm normalized_unit chuẩn để so sánh bia VN)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class NormalizedPrice:
    regular_price: float
    pack_quantity: float
    unit_volume_ml: float
    effective_price: float
    promotion_price: float | None
    price_per_unit: float
    price_per_liter: float
    price_per_100ml: float  # comparable measure
    normalized_unit: str = "per_100ml"


def normalize_price(
    regular_price: float,
    pack_quantity: float,
    unit_volume_ml: float,
    *,
    promotion_price: float | None = None,
    effective_price: float | None = None,
) -> NormalizedPrice:
    """Chuẩn hóa một giá pack thành các measure có thể so sánh.

    - pack_quantity: số lon/chai trong 1 thùng (ví dụ 24)
    - unit_volume_ml: thể tích 1 lon (ví dụ 330)
    - Nếu effective_price None -> lấy promotion_price nếu có, ngược lại regular.
    """
    if pack_quantity <= 0:
        raise ValueError("pack_quantity phải > 0")
    if unit_volume_ml <= 0:
        raise ValueError("unit_volume_ml phải > 0")

    total_volume_ml = pack_quantity * unit_volume_ml
    eff = effective_price
    if eff is None:
        eff = promotion_price if promotion_price is not None else regular_price
    price_per_unit = eff / pack_quantity
    price_per_liter = eff / (total_volume_ml / 1000.0)
    price_per_100ml = eff / (total_volume_ml / 100.0)

    return NormalizedPrice(
        regular_price=regular_price,
        pack_quantity=pack_quantity,
        unit_volume_ml=unit_volume_ml,
        effective_price=eff,
        promotion_price=promotion_price,
        price_per_unit=round(price_per_unit, 2),
        price_per_liter=round(price_per_liter, 2),
        price_per_100ml=round(price_per_100ml, 2),
    )


def comparable_key(pack_size: str | None, volume_ml: float | None) -> str:
    """Tạo comparable universe key (Spec §10).

    Ví dụ: '330ml x24' -> '330x24'. SKU khác quy cách (500ml x24) sinh
    key khác nên KHÔNG được tự động đưa vào cùng comparable group.
    """
    if volume_ml is None:
        return "unknown"
    return f"{int(volume_ml)}ml"
