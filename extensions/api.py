"""api.py — FastAPI web layer cho HMIP.

Bọc kernel HMIP (chạy-rồi-thoát) bằng một lớp HTTP, KHÔNG biến kernel
thành server. Mỗi request `/api/run` khởi tạo một execution mới đúng
như thiết kế gốc — WorkflowEngine tạo TaskRegistry riêng cho từng lần
chạy, nên an toàn khi gọi nhiều lần.

Từ v1.1.0: thêm quét tự động (auto-scan) chạy nền qua APScheduler,
gửi cảnh báo đẩy (Telegram hoặc log fallback).

Chạy:
    uvicorn extensions.api:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from extensions import db
from extensions.collect_adapters import COLLECT_MODE, _DEMO_CATALOG
from extensions.notifiers.telegram import is_configured as telegram_configured
from extensions.run_workflow import resolve_base_price, run_prc_001
from extensions.scheduler import scan_once
from extensions.auth import protect_app
from extensions.pi import service as pi_service

_STATIC_DIR = Path(__file__).resolve().parent / "web"
log = logging.getLogger("hmip.api")

_auto_scheduler = BackgroundScheduler()
_auto_job_id = "hmip_auto_scan"


def _auto_scan_job() -> None:
    try:
        scan_once()
    except Exception as exc:  # noqa: BLE001
        log.exception("auto-scan lỗi: %s", exc)


def _pi_collect_job() -> None:
    """Job nền (B): quét giá thật từ Tiki định kỳ, detect event + notify."""
    try:
        from extensions.pi import collectors as _col
        from extensions.pi import events as _ev
        r = _col.collect_realtime(channel="TIKI", limit=None)
        log.info("PI Tiki collect: %s", r)
        # Re-detect events/alerts trên data mới (best-effort)
        _ev.detect_events(path=None)
    except Exception as exc:  # noqa: BLE001
        log.exception("PI collect job lỗi: %s", exc)


def _start_pi_collect(interval_min: int = 30) -> None:
    if _auto_scheduler.get_job("hmip_pi_collect"):
        return
    _auto_scheduler.add_job(
        _pi_collect_job,
        trigger=IntervalTrigger(minutes=interval_min),
        id="hmip_pi_collect", max_instances=1, coalesce=True,
        next_run_time=datetime.now() + timedelta(seconds=10),
    )
    if not _auto_scheduler.running:
        _auto_scheduler.start()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    # Tự seed Price Intelligence DB nếu rỗng (Render ephemeral FS: data reset
    # khi restart → cần tái lập từ catalog mỗi lần cold start).
    try:
        pi_service.ensure_ready()
    except Exception as exc:  # không block startup nếu seed lỗi
        print(f"[PI] seed skip/error: {exc}")
    # Tự động bật auto-scan nếu env yêu cầu (mặc định TẮT để user chủ động).
    if os.getenv("HMIP_AUTOSCAN", "off").lower() in ("1", "on", "true", "yes"):
        _start_auto_scan()
        # Job PI: quét giá thật từ Tiki định kỳ (B) + detect/notify.
        _start_pi_collect(int(os.getenv("HMIP_PI_COLLECT_MIN", "30")))
    yield
    if _auto_scheduler.running:
        _auto_scheduler.shutdown(wait=False)


def _start_auto_scan() -> dict[str, Any]:
    if _auto_scheduler.get_job(_auto_job_id) is not None:
        return {"status": "already_running"}
    interval = int(os.getenv("HMIP_SCAN_INTERVAL_MIN", "30"))
    _auto_scheduler.add_job(
        _auto_scan_job,
        trigger=IntervalTrigger(minutes=interval),
        id=_auto_job_id,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now() + timedelta(seconds=3),  # quét ngay sau 3s
    )
    if not _auto_scheduler.running:
        _auto_scheduler.start()
    return {"status": "started", "interval_minutes": interval}


def _stop_auto_scan() -> dict[str, Any]:
    if _auto_scheduler.get_job(_auto_job_id) is not None:
        _auto_scheduler.remove_job(_auto_job_id)
    if _auto_scheduler.running and not _auto_scheduler.get_jobs():
        _auto_scheduler.shutdown(wait=False)
    return {"status": "stopped"}


app = FastAPI(
    title="HMIP — Market Intelligence Platform",
    description="Giám sát giá sản phẩm, tự động ra quyết định ALERT/ESCALATE.",
    version="1.2.0",
    lifespan=lifespan,
)

# Bảo vệ API khi có HMIP_API_TOKEN (deploy cloud bắt buộc).
protect_app(app)


class RunRequest(BaseModel):
    product_id: str = Field(..., examples=["P123"])
    source: str = Field("demo", examples=["shopee", "tiki"])
    market: str = Field("VN")


# ---------------------------------------------------------------- API

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "collect_mode": COLLECT_MODE,
        "telegram": telegram_configured(),
        "auto_scan": _auto_scheduler.get_job(_auto_job_id) is not None,
    }


@app.get("/api/catalog")
def catalog() -> list[dict[str, Any]]:
    """Sản phẩm có thể theo dõi (khớp ontology master data)."""
    return [
        {
            "product_id": pid,
            "product_name": meta["product_name"],
            "brand": meta["brand"],
            "base_price": resolve_base_price(pid),
        }
        for pid, meta in _DEMO_CATALOG.items()
    ]


@app.get("/api/products")
def products() -> list[dict[str, Any]]:
    return db.get_products()


class AddProductRequest(BaseModel):
    product_id: str = Field(..., examples=["P789"], pattern=r"^[A-Za-z0-9_\-]+$")
    name: str = Field(..., examples=["Tiger Beer 330ml"])
    brand: str = Field("", examples=["Tiger"])
    source: str = Field("manual", examples=["shopee"])
    base_price: float | None = Field(
        None, description="Để trống = tự động lấy giá quét đầu làm mốc"
    )


@app.post("/api/products")
def add_product(req: AddProductRequest) -> dict[str, Any]:
    """Thêm sản phẩm mới để theo dõi (từ giao diện)."""
    db.add_product(
        req.product_id, req.name, req.brand or None, req.source, req.base_price
    )
    # Ghi vào ontology master để enrich (kernel) nhận diện được SP mới.
    # Chỉ thêm data entry, không sửa code core.
    synced = db.sync_to_ontology(req.product_id, req.name, req.brand or None)
    return {"status": "added", "product_id": req.product_id, "synced_to_ontology": synced}


@app.get("/api/latest")
def latest() -> list[dict[str, Any]]:
    """Giá mới nhất mỗi sản phẩm — dữ liệu chính của dashboard."""
    return db.get_latest()


@app.get("/api/history/{product_id}")
def history(product_id: str, limit: int = 100, since: str | None = None) -> list[dict[str, Any]]:
    rows = db.get_history(product_id, limit=limit, since=since)
    if not rows:
        raise HTTPException(404, f"chưa có dữ liệu giá cho '{product_id}'")
    return rows


@app.get("/api/chart")
def chart(range: str = "all") -> dict[str, Any]:
    """Dữ liệu biểu đồ lịch sử giá — nhóm theo sản phẩm, có lọc thời gian.

    `range`: '1h' | '24h' | '7d' | 'all'
    Trả về { range, products: {pid: {name, brand, points:[{t,price,delta,decision}]}} }
    """
    since = None
    if range in ("1h", "24h", "7d"):
        hours = {"1h": 1, "24h": 24, "7d": 168}[range]
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    raw = db.get_history_all(since=since, limit=2000)
    products = {}
    for pid, rows in raw.items():
        meta = db.get_products()
        name = pid
        brand = ""
        for p in meta:
            if p["id"] == pid:
                name = p["name"]
                brand = p["brand"] or ""
                break
        points = [
            {
                "t": r["captured_at"],
                "price": r["price"],
                "delta": r["delta_percent"],
                "decision": r["decision"],
            }
            for r in sorted(rows, key=lambda x: x["captured_at"])
        ]
        products[pid] = {"name": name, "brand": brand, "points": points}
    return {"range": range, "since": since, "products": products}


@app.get("/api/alerts")
def alerts(limit: int = 50) -> list[dict[str, Any]]:
    """Các lần quét cho ra quyết định khác IGNORE."""
    out: list[dict[str, Any]] = []
    for product in db.get_products():
        for row in db.get_history(product["id"], limit=limit):
            if row.get("decision") and row["decision"] != "IGNORE":
                out.append({**row, "product_name": product["name"], "brand": product.get("brand") or ""})
    out.sort(key=lambda r: r["captured_at"], reverse=True)
    return out[:limit]


@app.post("/api/run")
def run(req: RunRequest) -> dict[str, Any]:
    """Chạy WF-PRC-001 ngay cho 1 sản phẩm."""
    result = run_prc_001(req.product_id, req.source, req.market)
    if result.get("status") != "COMPLETED":
        raise HTTPException(
            422,
            {
                "status": result.get("status"),
                "error": result.get("error"),
                "compensation": result.get("compensation"),
            },
        )
    steps = result.get("steps", {})
    return {
        "execution_id": result["execution_id"],
        "status": result["status"],
        "decision": (steps.get("decide") or {}).get("decision"),
        "reason": (steps.get("decide") or {}).get("reason"),
        "price": (steps.get("compare") or {}).get("current_price"),
        "base_price": result.get("base_price"),
        "delta_percent": (steps.get("compare") or {}).get("delta_percent"),
        "notified": (result.get("output") or {}).get("notified"),
        "saved": result.get("saved"),
    }


@app.post("/api/run-all")
def run_all() -> dict[str, Any]:
    """Quét TẤT CẢ sản phẩm. Seed DB từ catalog mặc định nếu rỗng (Render ephemeral)."""
    # Đảm bảo mọi sản phẩm trong catalog được ghi vào DB (idempotent upsert).
    for pid, meta in _DEMO_CATALOG.items():
        db.add_product(
            pid,
            meta.get("product_name", pid),
            meta.get("brand", ""),
            "catalog",
        )
    products = db.get_products()
    pids = [p["id"] for p in products] or list(_DEMO_CATALOG.keys())
    results = []
    for pid in pids:
        try:
            r = run_prc_001(pid, "batch")
            steps = r.get("steps", {})
            results.append({
                "product_id": pid,
                "status": r["status"],
                "decision": (steps.get("decide") or {}).get("decision"),
                "price": (steps.get("compare") or {}).get("current_price"),
                "delta_percent": (steps.get("compare") or {}).get("delta_percent"),
            })
        except Exception as exc:  # noqa: BLE001
            results.append({"product_id": pid, "status": "ERROR", "error": str(exc)})
    return {"scanned": len(results), "results": results}


@app.post("/api/autoscan/start")
def autoscan_start() -> dict[str, Any]:
    """Bật quét tự động nền."""
    return _start_auto_scan()


@app.post("/api/autoscan/stop")
def autoscan_stop() -> dict[str, Any]:
    """Tắt quét tự động nền."""
    return _stop_auto_scan()


@app.get("/api/autoscan/status")
def autoscan_status() -> dict[str, Any]:
    return {
        "running": _auto_scheduler.get_job(_auto_job_id) is not None,
        "interval_minutes": int(os.getenv("HMIP_SCAN_INTERVAL_MIN", "30")),
        "telegram_configured": telegram_configured(),
    }


# ------------------------------------------------------------- Price Intelligence (PI, Spec v2.0)

class PIFilter(BaseModel):
    product_id: str | None = None
    brand_id: str | None = None
    channel_id: str | None = None
    region_id: str | None = None
    period: str | None = "90D"
    promotion_only: bool = False


@app.get("/api/price-intelligence/catalog")
def pi_catalog() -> dict[str, Any]:
    """Dimensions cho filter bar (Spec §5)."""
    return pi_service.get_catalog()


@app.get("/api/price-intelligence/overview")
def pi_overview(
    product_id: str | None = None, brand_id: str | None = None,
    channel_id: str | None = None, region_id: str | None = None,
    period: str | None = "90D",
) -> dict[str, Any]:
    return pi_service.overview({
        "product_id": product_id, "brand_id": brand_id,
        "channel_id": channel_id, "region_id": region_id, "period": period,
    })


@app.get("/api/price-intelligence/workspace")
def pi_workspace(
    product_id: str | None = None, brand_id: str | None = None,
    channel_id: str | None = None, region_id: str | None = None,
    period: str | None = "90D",
) -> dict[str, Any]:
    """Gom toàn bộ dashboard một lần gọi."""
    return pi_service.full_workspace({
        "product_id": product_id, "brand_id": brand_id,
        "channel_id": channel_id, "region_id": region_id, "period": period,
    })


@app.get("/api/prices/trend")
def pi_trend(
    product_id: str | None = None, channel_id: str | None = None,
    region_id: str | None = None, period: str | None = "90D",
    series: str | None = "sku_price,market_avg,brand_avg",
) -> dict[str, Any]:
    return pi_service.trend(
        {"product_id": product_id, "channel_id": channel_id,
         "region_id": region_id, "period": period},
        series=series.split(",") if series else None,
    )


@app.get("/api/prices/index")
def pi_index(
    product_id: str | None = None, channel_id: str | None = None,
    region_id: str | None = None, period: str | None = "90D",
    method: str = "median",
) -> dict[str, Any]:
    return pi_service.index(
        {"product_id": product_id, "channel_id": channel_id,
         "region_id": region_id, "period": period}, method=method)


@app.get("/api/prices/positioning")
def pi_positioning(
    product_id: str | None = None, channel_id: str | None = None,
    region_id: str | None = None, period: str | None = "90D",
) -> dict[str, Any]:
    return pi_service.positioning({
        "product_id": product_id, "channel_id": channel_id,
        "region_id": region_id, "period": period})


@app.get("/api/prices/sku/{sku_id}")
def pi_sku(sku_id: str, period: str | None = "ALL") -> dict[str, Any]:
    # sku_id ở đây thực tế là product_id (UI truyền product_id)
    return pi_service.sku_explorer(sku_id)


@app.get("/api/prices/channel-comparison")
def pi_channel(
    product_id: str | None = None, brand_id: str | None = None,
    region_id: str | None = None, period: str | None = "90D",
) -> dict[str, Any]:
    return pi_service.channel({
        "product_id": product_id, "brand_id": brand_id,
        "region_id": region_id, "period": period})


@app.get("/api/prices/regional")
def pi_region(
    product_id: str | None = None, brand_id: str | None = None,
    channel_id: str | None = None, period: str | None = "90D",
) -> dict[str, Any]:
    return pi_service.region({
        "product_id": product_id, "brand_id": brand_id,
        "channel_id": channel_id, "period": period})


@app.get("/api/prices/promotions")
def pi_promotions(
    product_id: str | None = None, channel_id: str | None = None,
    region_id: str | None = None, period: str | None = "90D",
) -> dict[str, Any]:
    return pi_service.promotions({
        "product_id": product_id, "channel_id": channel_id,
        "region_id": region_id, "period": period})


@app.get("/api/prices/events")
def pi_events(
    product_id: str | None = None, channel_id: str | None = None,
    region_id: str | None = None, event_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return pi_service.price_events({
        "product_id": product_id, "channel_id": channel_id,
        "region_id": region_id, "event_type": event_type}, limit=limit)


@app.get("/api/prices/alerts")
def pi_alerts(severity: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    return pi_service.alerts(severity=severity, limit=limit)


@app.post("/api/price-intelligence/seed")
def pi_seed(rebuild: bool = True) -> dict[str, Any]:
    """Seed (hoặc rebuild) dữ liệu thị trường PI."""
    if rebuild:
        return pi_service.rebuild()
    return pi_service.ensure_ready()


@app.post("/api/ai/price-analysis")
def pi_ai_analysis(
    event_id: str | None = None,
    question: str | None = None,
    product_id: str | None = None,
) -> dict[str, Any]:
    """AI Analyst (Spec §27). Cần event_id hoặc (question + product_id)."""
    if event_id:
        return pi_service.ai_analyze(event_id)
    if question:
        return pi_service.ai_ask(question, product_id)
    raise HTTPException(422, "cần event_id hoặc question")


@app.post("/api/prices/collect")
def pi_collect(channel: str = "TIKI", limit: int | None = None) -> dict[str, Any]:
    """Quét giá THẬT từ sàn (hiện Tiki hoạt động; Shopee/Lazada cần key).

    Thay thế seed demo bằng data thực. Trả summary {collected, failed, total}.
    """
    from extensions.pi import collectors as _col
    try:
        return _col.collect_realtime(channel=channel.upper(), limit=limit)
    except NotImplementedError as exc:
        raise HTTPException(501, str(exc))


# ------------------------------------------------------------- static

if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    _PI_DIR = Path(__file__).resolve().parent / "web"

    @app.get("/pi")
    def pi_dashboard() -> FileResponse:
        return FileResponse(_PI_DIR / "pi.html")
