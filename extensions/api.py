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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from extensions import db
from extensions.auth import protect_app
from extensions.collect_adapters import _DEMO_CATALOG, COLLECT_MODE
from extensions.notifiers.discord import is_configured as discord_configured
from extensions.notifiers.telegram import is_configured as telegram_configured
from extensions.pi import service as pi_service
from extensions.run_workflow import resolve_base_price, run_prc_001
from extensions.scheduler import scan_once

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
    """Job nền (B): quét giá thật (chain 4-tier) định kỳ + detect/notify.

    Lần đầu: cào 1 lần ghi toàn bộ observation, đánh dấu marker (giá thật gốc).
    Các lần sau: chỉ ghi observation khi giá thay đổi + notify Telegram/Discord.
    Dừng tại tier đầu tiên thành công: Firecrawl → ScraperAPI → ZenRows → Jina.
    """
    try:
        import os as _os

        from extensions.pi import collectors as _col
        _path = _os.getenv("HMIP_PI_DB_PATH") or None
        r = _col.collect_realtime_smart(limit=None, path=_path)
        log.info("PI collect: %s", r)
        from extensions.pi import events as _ev
        _ev.detect_events(path=_path)
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
    # Backfill brand_id rỗng trong observation cũ (pre-PR#12) từ
    # pi_products.brand_id → tránh "Unknown" brand trong Competitor Comparison
    # / Price Index. Idempotent: chỉ update row có brand_id rỗng.
    try:
        from extensions.pi import pi_store as _ps
        _migrated = _ps.migrate_brand_ids(
            path=os.getenv("HMIP_PI_DB_PATH") or None)
        if _migrated:
            print(f"[PI] migrated brand_id cho {_migrated} observation(s)")
    except Exception as _exc:
        print(f"[PI] brand_id migrate skip/error: {_exc}")
    # Tự seed Price Intelligence DB nếu rỗng + env HMIP_PI_AUTOSEED != off.
    # MẶC ĐỊNH BẬT (on): Render ephemeral FS mất data mỗi restart -> tự seed
    # lại để user vào web luôn có data, không cần bấm Seed thủ công.
    # Đã fix OOM: seed chunked + 30 ngày (~184k rows, RAM ~100MB) + chạy
    # BẤT ĐỒNG BỘ (background thread) không block startup, an toàn 512Mi.
    # Tắt bằng env HMIP_PI_AUTOSEED=off nếu muốn seed thủ công hoàn toàn.
    #
    # GIỮ CỐ ĐỊNH GIÁ THẬT: nếu đã cào giá thật lần đầu (marker đặt) thì
    # KHÔNG re-seed synthetic — giữ dữ liệu thật cố định qua các lần restart.
    try:
        if os.getenv("HMIP_PI_AUTOSEED", "on").lower() not in ("0", "off", "false", "no"):
            _pi_path = os.getenv("HMIP_PI_DB_PATH") or None
            _has_real = False
            try:
                from extensions.pi import persistent_collector as _pc
                _has_real = _pc.has_real_prices(path=_pi_path)
            except Exception:
                pass
            if _has_real:
                # Đã có giá thật → giữ cố định, không re-seed synthetic.
                pi_service.mark_ready(path=_pi_path)
                print("[PI] Đã có giá thật (marker) → giữ cố định, không re-seed")
            elif pi_service.seed_status()["status"] == "idle":
                obs = pi_service.ensure_ready_count(path=_pi_path)
                if obs == 0:
                    pi_service.seed_async()
                else:
                    pi_service.mark_ready(path=_pi_path)
        # Backfill kênh mới (PR #13: registry 18→24) trên DB đã seed/đã có giá
        # thật — thêm observation cho kênh chưa có data, KHÔNG xoá data thật.
        # Idempotent: noop nếu mọi kênh đã có observation.
        try:
            from extensions.pi.seed import backfill_new_channels as _bf
            _bf_r = _bf(path=os.getenv("HMIP_PI_DB_PATH") or None)
            if _bf_r.get("status") == "backfilled":
                print(f"[PI] backfilled {_bf_r['new_channels']} "
                      f"({_bf_r['observations']} obs)")
        except Exception as _exc:
            print(f"[PI] backfill skip/error: {_exc}")
        # Dọn contamination box-as-lon lịch sử (pre-guard): chuẩn hoá obs có
        # giá thùng lưu làm giá/lon + xoá events/alerts giả. Idempotent.
        try:
            from extensions.pi.persistent_collector import cleanup_box_contamination as _cb
            _cb_r = _cb(path=os.getenv("HMIP_PI_DB_PATH") or None)
            if _cb_r["normalized_observations"] or _cb_r["deleted_events"]:
                print(f"[PI] cleaned box-contamination: "
                      f"{_cb_r['normalized_observations']} obs normalized, "
                      f"{_cb_r['deleted_events']} events, "
                      f"{_cb_r['deleted_alerts']} alerts")
        except Exception as _exc:
            print(f"[PI] cleanup skip/error: {_exc}")
    except Exception as exc:  # không block startup nếu seed lỗi
        print(f"[PI] seed skip/error: {exc}")
    # Tự động bật auto-scan nếu env yêu cầu (mặc định TẮT để user chủ động).
    if os.getenv("HMIP_AUTOSCAN", "off").lower() in ("1", "on", "true", "yes"):
        _start_auto_scan()
        # Job PI: quét giá thật (chain 4-tier) định kỳ + detect/notify.
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
        "discord": discord_configured(),
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
        since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
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
        "discord_configured": discord_configured(),
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


@app.get("/api/prices/index-trend")
def pi_index_trend(
    product_id: str | None = None, brand_id: str | None = None,
    channel_id: str | None = None, region_id: str | None = None,
    period: str | None = "90D",
) -> dict[str, Any]:
    """Price Index time-series (Roadmap Bước 2 / v3.1 §2).

    Baseline = giá trung bình ngày đầu window (index=100). Trả series daily
    để vẽ biểu đồ xu hướng giá.
    """
    from extensions.pi import analytics
    return analytics.price_index_trend(
        {"product_id": product_id, "brand_id": brand_id, "channel_id": channel_id,
         "region_id": region_id, "period": period})


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
    """Seed dữ liệu PI bất đồng bộ (chạy nền, tránh Render request timeout).
    Trả ngay 202-style; frontend poll /api/price-intelligence/status để theo dõi."""
    if rebuild:
        return pi_service.seed_async()
    return pi_service.ensure_ready()


@app.get("/api/price-intelligence/status")
def pi_seed_status() -> dict[str, Any]:
    """Trạng thái seed hiện tại (idle/running/done/error)."""
    return pi_service.seed_status()


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


@app.post("/api/prices/reset")
def pi_reset() -> dict[str, Any]:
    """Xóa toàn bộ observation/event/alert (demo) — giữ nguyên catalog schema.

    Dùng khi muốn chuyển 100% sang giá thật (không demo). Sau reset, gọi
    /api/prices/collect để nạp data thật từ Firecrawl.
    """
    from extensions.pi import pi_store as _ps
    try:
        path = os.getenv("HMIP_PI_DB_PATH") or None
        _ps.clear_observations(path=path)
        return {"status": "reset_done", "msg": "Đã xóa observation/event/alert demo"}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/prices/collect")
def pi_collect(channel: str = "TIKI", limit: int | None = None) -> dict[str, Any]:
    """Quét giá THẬT bất đồng bộ (background thread, tránh Render request timeout).

    Dùng collect_realtime_smart: Firecrawl trước (circuit breaker skip 402),
    fallback ScraperAPI Tiki API. Trả ngay status=started; client poll
    /api/price-intelligence/overview để xem dữ liệu mới.
    """
    import os as _os
    import threading
    _path = _os.getenv("HMIP_PI_DB_PATH") or None
    from extensions.pi import collectors as _col
    from extensions.pi import events as _ev

    def _bg():
        try:
            r = _col.collect_realtime_smart(limit=limit, path=_path)
            log.info("PI collect (trigger): %s", r)
            _ev.detect_events(path=_path)
        except Exception as exc:  # noqa: BLE001
            log.exception("PI collect trigger lỗi: %s", exc)

    threading.Thread(target=_bg, daemon=True).start()
    return {"status": "started", "limit": limit,
            "msg": "Đang quét nền. Poll /api/price-intelligence/overview sau 2-3 phút."}


# ----------------------- auto-scan khi vào trang (scan-if-stale) -----------
# Tránh quét lại nếu dữ liệu còn mới (user refresh liên tục). Flag in-memory
# chống trigger trùng (2 tab cùng vào) — reset khi scan xong.

_AUTO_SCAN_IN_PROGRESS = False
_AUTO_PI_COLLECT_IN_PROGRESS = False


def _stale_minutes() -> float:
    """Cửa sổ 'fresh' (phút). Dữ liệu mới hơn cửa sổ này → không quét lại.
    Env `HMIP_AUTO_SCAN_STALE_MIN` (mặc định 5'). 0 = luôn quét."""
    try:
        return float(os.getenv("HMIP_AUTO_SCAN_STALE_MIN", "5"))
    except ValueError:
        return 5.0


def _latest_scan_ts() -> datetime | None:
    """Timestamp observation mới nhất trong DB chính (trang chủ /)."""
    try:
        db.init_db()  # đảm bảo schema tồn tại (DB Render ephemeral có thể rỗng)
        latest = db.get_latest()
    except Exception:  # noqa: BLE001
        return None
    ts = None
    for row in latest:
        cap = row.get("captured_at")
        if cap:
            try:
                t = datetime.fromisoformat(cap)
                if ts is None or t > ts:
                    ts = t
            except (ValueError, TypeError):
                continue
    return ts


def _latest_pi_obs_ts() -> datetime | None:
    """Timestamp observation PI mới nhất (trang /pi, /workspace)."""
    try:
        from extensions.pi import pi_store
        _path = os.getenv("HMIP_PI_DB_PATH") or None
        rows = pi_store.fetch_all(
            "SELECT MAX(observed_at) AS m FROM pi_observations", [],
            path=_path,
        )
        if rows and rows[0].get("m"):
            return datetime.fromisoformat(rows[0]["m"])
    except Exception:  # noqa: BLE001
        pass
    return None


@app.post("/api/scan-if-stale")
def scan_if_stale() -> dict[str, Any]:
    """Tự quét (run-all) nền nếu dữ liệu cũ/empty — gọi khi user vào trang /.

    Trả ``triggered=true`` nếu đã kick scan background (user nên poll
    ``/api/latest`` để xem dữ liệu mới). Trả ``triggered=false`` nếu dữ liệu
    còn fresh (không quét lại — tránh spam Render/credit khi refresh).
    """
    global _AUTO_SCAN_IN_PROGRESS
    stale_min = _stale_minutes()
    last = _latest_scan_ts()
    now = datetime.now(UTC)
    is_stale = (
        last is None
        or (now - (last if last.tzinfo else last.replace(tzinfo=UTC)))
        > timedelta(minutes=stale_min)
    )
    if not is_stale:
        return {"triggered": False, "reason": "fresh",
                "last_scan": (last.isoformat() if last else None)}
    if _AUTO_SCAN_IN_PROGRESS:
        return {"triggered": False, "reason": "already-scanning",
                "last_scan": (last.isoformat() if last else None)}

    import threading

    def _bg_run_all() -> None:
        global _AUTO_SCAN_IN_PROGRESS
        try:
            for pid, meta in _DEMO_CATALOG.items():
                db.add_product(pid, meta.get("product_name", pid),
                               meta.get("brand", ""), "catalog")
            products = db.get_products()
            pids = [p["id"] for p in products] or list(_DEMO_CATALOG.keys())
            for pid in pids:
                try:
                    run_prc_001(pid, "batch")
                except Exception as exc:  # noqa: BLE001
                    log.warning("Auto-scan run_prc_001 %s lỗi: %s", pid, exc)
            log.info("Auto-scan-if-stale xong: %d SP", len(pids))
        except Exception as exc:  # noqa: BLE001
            log.exception("Auto-scan-if-stale lỗi: %s", exc)
        finally:
            _AUTO_SCAN_IN_PROGRESS = False

    _AUTO_SCAN_IN_PROGRESS = True
    threading.Thread(target=_bg_run_all, daemon=True).start()
    return {"triggered": True, "reason": "stale" if last else "empty",
            "last_scan": (last.isoformat() if last else None),
            "msg": "Đang quét nền. Dữ liệu sẽ cập nhật sau vài giây."}


@app.post("/api/price-intelligence/collect-if-stale")
def pi_collect_if_stale(limit: int | None = None) -> dict[str, Any]:
    """Tự thu thập giá PI nền nếu dữ liệu PI cũ/empty — gọi khi vào /pi, /workspace.

    Trả ``triggered=true`` nếu đã kick collect background (poll
    ``/api/price-intelligence/overview``). Trả ``triggered=false`` nếu fresh.
    """
    global _AUTO_PI_COLLECT_IN_PROGRESS
    stale_min = _stale_minutes()
    last = _latest_pi_obs_ts()
    now = datetime.now(UTC)
    is_stale = (
        last is None
        or (now - (last if last.tzinfo else last.replace(tzinfo=UTC)))
        > timedelta(minutes=stale_min)
    )
    if not is_stale:
        return {"triggered": False, "reason": "fresh",
                "last_scan": (last.isoformat() if last else None)}
    if _AUTO_PI_COLLECT_IN_PROGRESS:
        return {"triggered": False, "reason": "already-collecting",
                "last_scan": (last.isoformat() if last else None)}

    import os as _os
    import threading
    _path = _os.getenv("HMIP_PI_DB_PATH") or None
    from extensions.pi import collectors as _col
    from extensions.pi import events as _ev

    def _bg() -> None:
        global _AUTO_PI_COLLECT_IN_PROGRESS
        try:
            r = _col.collect_realtime_smart(limit=limit, path=_path)
            log.info("PI collect-if-stale xong: %s", r)
            _ev.detect_events(path=_path)
        except Exception as exc:  # noqa: BLE001
            log.exception("PI collect-if-stale lỗi: %s", exc)
        finally:
            _AUTO_PI_COLLECT_IN_PROGRESS = False

    _AUTO_PI_COLLECT_IN_PROGRESS = True
    threading.Thread(target=_bg, daemon=True).start()
    return {"triggered": True, "reason": "stale" if last else "empty",
            "last_scan": (last.isoformat() if last else None),
            "msg": "Đang thu thập giá nền. Poll /api/price-intelligence/overview."}


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

    @app.get("/workspace")
    def workspace_dashboard() -> FileResponse:
        return FileResponse(_PI_DIR / "pi.html")
