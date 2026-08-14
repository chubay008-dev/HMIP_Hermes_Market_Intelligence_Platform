"""service.py — Price Intelligence orchestration & API payload builders.

Đóng gói toàn bộ pipeline (Spec §6, §64):
    seed → normalize (trong seed) → detect events → store → analytics → API

Cung cấp các hàm build payload cho FastAPI (api.py) theo spec §40
(endpoints /api/price-intelligence/*, /api/prices/*, /api/ai/*).

Không sửa code core/domains. Chỉ gọi extensions.pi.* (tầng bọc ngoài).
"""

from __future__ import annotations

import threading
import time
from typing import Any

from extensions.pi import pi_store, seed, analytics, events, ai_analyst


# ---- Seed background state (tránh Render request timeout do seed chạy đồng bộ) ----
_seed_lock = threading.Lock()
_seed_state: dict[str, Any] = {"status": "idle", "message": "", "detail": None}

# ---- In-memory TTL cache cho analytics (giảm ~9s → ms khi filter không đổi) ----
_cache_lock = threading.Lock()
_cache: dict[tuple, tuple[float, Any]] = {}
_CACHE_TTL = 60.0  # giây


def _cache_get(key: tuple) -> Any | None:
    with _cache_lock:
        ent = _cache.get(key)
        if ent and (time.monotonic() - ent[0]) < _CACHE_TTL:
            return ent[1]
        if ent:
            _cache.pop(key, None)
        return None


def _cache_set(key: tuple, val: Any) -> Any:
    with _cache_lock:
        _cache[key] = (time.monotonic(), val)
    return val


def invalidate_cache() -> None:
    """Xoá cache khi dữ liệu thay đổi (seed/rebuild/scan)."""
    with _cache_lock:
        _cache.clear()


def seed_status() -> dict[str, Any]:
    """Trả trạng thái seed hiện tại (cho frontend poll)."""
    with _seed_lock:
        return dict(_seed_state)


def _run_seed():
    global _seed_state
    try:
        with _seed_lock:
            _seed_state = {"status": "running", "message": "Đang tạo dữ liệu thị trường...", "detail": None}
        res = rebuild()
        with _seed_lock:
            _seed_state = {"status": "done", "message": "Seed xong", "detail": res}
    except Exception as e:  # noqa: BLE001
        with _seed_lock:
            _seed_state = {"status": "error", "message": f"Lỗi seed: {e}", "detail": repr(e)}


def seed_async() -> dict[str, Any]:
    """Bắt đầu seed bất đồng bộ (thread). Trả ngay, không chờ."""
    with _seed_lock:
        if _seed_state["status"] == "running":
            return {"status": "running", "message": "Seed đang chạy"}
    t = threading.Thread(target=_run_seed, daemon=True)
    t.start()
    return {"status": "started", "message": "Đã bắt đầu seed (chạy nền)"}


def ensure_ready_count(path: str | None = None) -> int:
    """Đếm số observation hiện có (không seed). Dùng để quyết định có auto-seed không."""
    try:
        pi_store.init_pi_db(path)
        return pi_store.count_rows("pi_observations", path=path)
    except Exception:
        return 0


def mark_ready(path: str | None = None) -> dict[str, Any]:
    """DB đã có data sẵn -> đánh dấu trạng thái seed là done (không chạy lại)."""
    global _seed_state
    with _seed_lock:
        if _seed_state["status"] == "running":
            return dict(_seed_state)
        obs = pi_store.count_rows("pi_observations", path=path)
        _seed_state = {"status": "done", "message": "Seed sẵn có", "detail": {"observations": obs}}
    return dict(_seed_state)


def ensure_ready(path: str | None = None) -> dict[str, Any]:
    """Đảm bảo DB PI đã init + có dữ liệu. Nếu rỗng -> seed."""
    pi_store.init_pi_db(path)
    obs = pi_store.count_rows("pi_observations", path=path)
    if obs == 0:
        return seed.seed_full(path=path)
    return {"status": "already_seeded", "observations": obs}


def rebuild(path: str | None = None) -> dict[str, Any]:
    """Xoá + seed lại + detect events. Dùng khi muốn dữ liệu mới."""
    res = seed.seed_full(path=path)
    det = events.detect_events(rerun=True, path=path)
    invalidate_cache()
    return {**res, **det}


def overview(filters: dict[str, Any] | None = None, path: str | None = None) -> dict[str, Any]:
    return analytics.kpi_overview(filters, path=path)


def trend(filters: dict[str, Any] | None = None, series: list[str] | None = None,
          path: str | None = None) -> dict[str, Any]:
    return analytics.price_trend(filters, series, path=path)


def index(filters: dict[str, Any] | None = None, method: str = "median",
          path: str | None = None) -> dict[str, Any]:
    return analytics.price_index_by_brand(filters, method, path=path)


def positioning(filters: dict[str, Any] | None = None, path: str | None = None) -> dict[str, Any]:
    return analytics.positioning_matrix(filters, path=path)


def competitor(filters: dict[str, Any] | None = None, path: str | None = None) -> dict[str, Any]:
    return analytics.competitor_comparison(filters, path=path)


def channel(filters: dict[str, Any] | None = None, path: str | None = None) -> dict[str, Any]:
    return analytics.channel_comparison(filters, path=path)


def region(filters: dict[str, Any] | None = None, path: str | None = None) -> dict[str, Any]:
    return analytics.regional_pricing(filters, path=path)


def promotions(filters: dict[str, Any] | None = None, path: str | None = None) -> dict[str, Any]:
    return analytics.promotion_intelligence(filters, path=path)


def price_events(filters: dict[str, Any] | None = None, limit: int = 100,
                path: str | None = None) -> list[dict[str, Any]]:
    return events.list_events(filters, limit, path=path)


def alerts(severity: str | None = None, limit: int = 100,
           path: str | None = None) -> list[dict[str, Any]]:
    return events.list_alerts(severity, limit, path=path)


def sku_explorer(sku_id: str, path: str | None = None) -> dict[str, Any]:
    """SKU Explorer payload (Spec §18, §37): header + history + competitor +
    channel + promotion + events + (AI hook riêng).

    `sku_id` ở đây là product_id (UI truyền product_id, ví dụ 'P123').
    Nếu truyền dạng 'SKU-P123' sẽ tự strip prefix.
    """
    product_id = sku_id
    if product_id.startswith("SKU-"):
        product_id = product_id[4:]
    meta = pi_store.fetch_one(
        "SELECT p.*, b.name AS brand FROM pi_products p "
        "JOIN pi_brands b ON b.brand_id = p.brand_id WHERE p.product_id = ?",
        (product_id,), path=path)
    if not meta:
        return {"status": "error", "message": "product not found"}
    history = analytics.price_trend(filters={"product_id": product_id, "period": "ALL"},
                                    series=["sku_price", "market_avg", "brand_avg"], path=path)
    comp = competitor(filters={"product_id": product_id}, path=path)
    ch = channel(filters={"product_id": product_id}, path=path)
    promo = promotions(filters={"product_id": product_id}, path=path)
    evs = price_events(filters={"product_id": product_id}, limit=20, path=path)
    return {
        "product": dict(meta),
        "history": history,
        "competitor": comp,
        "channel": ch,
        "promotions": promo,
        "events": evs,
    }


def ai_analyze(event_id: str, path: str | None = None) -> dict[str, Any]:
    return ai_analyst.analyze_event(event_id, path=path)


def ai_ask(question: str, product_id: str | None = None,
           path: str | None = None) -> dict[str, Any]:
    return ai_analyst.ask_question(question, product_id, path=path)


def get_catalog(path: str | None = None) -> dict[str, Any]:
    return analytics.catalog(path=path)


def full_workspace(filters: dict[str, Any] | None = None, path: str | None = None) -> dict[str, Any]:
    """Gom tất cả cho dashboard một lần gọi (giảm số round-trip).

    Cache in-memory TTL 60s theo filter set: request đầu ~9s, các request lặp
    trong 60s tiếp theo trả ngay (ms). Cache tự xoá khi rebuild/seed."""
    key = ("full_workspace", _norm_filters(filters), path)
    hit = _cache_get(key)
    if hit is not None:
        return hit
    payload = {
        "kpi": overview(filters, path=path),
        "trend": trend(filters, path=path),
        "index": index(filters, path=path),
        "competitor": competitor(filters, path=path),
        "channel": channel(filters, path=path),
        "region": region(filters, path=path),
        "positioning": positioning(filters, path=path),
        "promotions": promotions(filters, path=path),
        "events": price_events(filters, limit=30, path=path),
        "alerts": alerts(limit=30, path=path),
    }
    return _cache_set(key, payload)


def _norm_filters(f: dict[str, Any] | None) -> tuple:
    """Bộ lọc None hoặc {} đều ra cùng key tránh cache miss."""
    if not f:
        return ()
    return tuple(sorted((k, str(v)) for k, v in f.items() if v is not None))
