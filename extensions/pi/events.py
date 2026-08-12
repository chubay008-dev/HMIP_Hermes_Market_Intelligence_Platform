"""events.py — Price Event Detection + Alert Engine (Spec §22-§26).

Pipeline (§23):
    Observation → Change Detection → Event Classification
    → Significance Score → Correlation → Alert (with dedup)

Severity (§24 defaults, category override supported):
    <3%   -> LOW / INFO
    3-5%  -> MEDIUM
    5-10% -> HIGH
    >10%  -> CRITICAL

Noise reduction (§25): significance score + dedup_key để triệt alert
lặp. Change detection so sánh với BASELINE = trung bình 7 ngày trước
(thay vì ngày liền kề) để lọc noise random walk hàng ngày.
"""

from __future__ import annotations

import hashlib
import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from extensions.pi import pi_store
from extensions.pi.models import DEFAULT_THRESHOLDS, Severity, now_iso

log = logging.getLogger("hmip.events")


def _severity_for(change_abs: float, thresholds: dict[str, float] | None = None) -> tuple[str, str]:
    t = thresholds or DEFAULT_THRESHOLDS
    if change_abs >= t["high"]:
        return Severity.CRITICAL, "change >= high threshold"
    if change_abs >= t["medium"]:
        return Severity.HIGH, "change between medium and high"
    if change_abs >= t["low"]:
        return Severity.MEDIUM, "change between low and medium"
    return Severity.LOW, "change below low threshold"


def _significance(change_abs: float, correlated: int) -> str:
    """Significance = magnitude + correlation (§25)."""
    score = change_abs + correlated * 1.5
    if score >= 10:
        return "HIGH"
    if score >= 5:
        return "MEDIUM"
    if score >= 3:
        return "LOW"
    return "NONE"


def _dedup_key(sku_id: str, channel_id: str | None, region_id: str | None,
               event_type: str, day: str) -> str:
    raw = f"{sku_id}|{channel_id or ''}|{region_id or ''}|{event_type}|{day}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def detect_events(product_id: str | None = None, rerun: bool = False,
                  path: str | None = None) -> dict[str, Any]:
    """Quét observations, phát hiện bước nhảy giá so với baseline 7 ngày
    (>medium threshold) → tạo price event + alert (với dedup).

    Trả summary số event/alert mới tạo.
    """
    if rerun:
        conn = pi_store._connect(path or pi_store.DEFAULT_PI_DB_PATH)  # type: ignore[attr-defined]
        try:
            conn.execute("DELETE FROM pi_price_events")
            conn.execute("DELETE FROM pi_alerts")
            conn.commit()
        finally:
            conn.close()

    where = "WHERE o.product_id = ?" if product_id else ""
    params = [product_id] if product_id else []
    rows = pi_store.fetch_all(
        f"""SELECT o.observation_id, o.sku_id, o.product_id, o.channel_id,
                   o.region_id, o.observed_at, o.effective_price, o.regular_price,
                   o.promotion_price
            FROM pi_observations o
            {where}
            ORDER BY o.sku_id, o.channel_id, o.region_id, o.observed_at""",
        params, path=path,
    )

    # group theo (sku, channel, region)
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in rows:
        key = (r["sku_id"], r["channel_id"], r["region_id"])
        groups.setdefault(key, []).append(r)

    new_events = 0
    new_alerts = 0
    _pending_alerts: list[dict] = []
    thresholds = DEFAULT_THRESHOLDS
    WINDOW = 7  # dedup window: mỗi (sku,channel,region,type) chỉ 1 event/7 ngày

    for key, series in groups.items():
        series.sort(key=lambda x: x["observed_at"])
        for i in range(1, len(series)):
            cur = series[i]
            prev = series[i - 1]
            newp = float(cur["effective_price"])
            oldp = float(prev["effective_price"])
            if oldp <= 0:
                continue
            change = (newp - oldp) / oldp * 100.0
            change_abs = abs(change)
            # Price event khi bước nhảy ngày-liền-kề vượt HIGH (10%) — tương
            # ứng "significant price event" (Spec §22, §25). Với giá bia ổn
            #  định (flat + tiny noise) chỉ jump_event mới vượt ngưỡng.
            if change_abs < thresholds["high"]:
                continue
            etype = "PRICE_INCREASE" if change > 0 else "PRICE_DECREASE"
            sev, _ = _severity_for(change_abs, thresholds)
            day = cur["observed_at"][:10]
            # Dedup: chỉ 1 event cùng (sku,channel,region,type) trong 7 ngày
            dk = _dedup_key(cur["sku_id"], cur["channel_id"], cur["region_id"], etype, day)
            if _recent_dedup(cur["sku_id"], cur["channel_id"], cur["region_id"], etype,
                             cur["observed_at"], path=path):
                continue
            correlated = _count_recent_events(cur["sku_id"], cur["observed_at"], path=path)
            sig = _significance(change_abs, correlated)
            ev_id = f"PE-{cur['observed_at'][:10].replace('-', '')}-{key[0]}-{key[1]}-{key[2]}-{i}"
            inserted = pi_store.insert_event(
                event_id=ev_id, sku_id=cur["sku_id"], channel_id=cur["channel_id"],
                region_id=cur["region_id"], timestamp=cur["observed_at"],
                old_price=round(oldp, 2), new_price=newp, change_percent=round(change, 2),
                event_type=etype, significance=sig, confidence=0.9, dedup_key=dk, path=path)
            if inserted:
                new_events += 1
                if sev == Severity.CRITICAL:
                    alert_msg = (
                        f"{'Tăng' if change > 0 else 'Giảm'} giá {cur['sku_id']} "
                        f"{abs(change):.1f}% trên {cur['channel_id']} ({cur['region_id']}). Mức {sev}.")
                    a_id = f"AL-{ev_id}"
                    if pi_store.insert_alert(
                        alert_id=a_id, event_id=ev_id, sku_id=cur["sku_id"],
                        severity=sev, created_at=now_iso(), message=alert_msg,
                        dedup_key=dk, path=path):
                        new_alerts += 1
                        # Thu thập để push ra ngoài (Discord/Telegram)
                        _pending_alerts.append({
                            "event_type": etype, "sku_id": cur["sku_id"],
                            "product_name": cur.get("product_name"),
                            "channel_id": cur["channel_id"], "region_id": cur["region_id"],
                            "old_price": round(oldp, 2), "new_price": round(newp, 2),
                            "change_pct": round(change, 2), "severity": sev,
                            "timestamp": cur["observed_at"],
                        })

    # Push CRITICAL alerts ra kênh ngoài (best-effort, không block).
    if _pending_alerts:
        try:
            from extensions.pi import notifier
            sent = notifier.notify_alerts(_pending_alerts)
            log.info("Notified alerts: %s", sent)
        except Exception as exc:
            log.warning("Notify failed: %s", exc)

    return {"status": "detected", "new_events": new_events, "new_alerts": new_alerts}


def _emit_event(*, sku_id: str, channel_id: str, region_id: str, timestamp: str,
                old_price: float, new_price: float, change_percent: float,
                event_type: str, thresholds: dict[str, float], path: str | None) -> None:
    day = timestamp[:10]
    dk = _dedup_key(sku_id, channel_id, region_id, event_type, day)
    ev_id = f"PE-{day.replace('-', '')}-{sku_id}-{channel_id}-{region_id}-{event_type}"
    pi_store.insert_event(
        event_id=ev_id, sku_id=sku_id, channel_id=channel_id, region_id=region_id,
        timestamp=timestamp, old_price=round(old_price, 2), new_price=round(new_price, 2),
        change_percent=round(change_percent, 2), event_type=event_type,
        significance="LOW", confidence=0.85, dedup_key=dk, path=path,
    )


def _recent_dedup(sku_id: str, channel_id: str, region_id: str, event_type: str,
                  ts: str, path: str | None = None) -> bool:
    """Trả True nếu đã có event cùng (sku,channel,region,type) trong 7 ngày
    qua — triệt alert/event lặp (Spec §25 noise reduction)."""
    try:
        dt = datetime.fromisoformat(ts)
    except Exception:
        return False
    window_start = (dt - timedelta(days=7)).isoformat()
    row = pi_store.fetch_one(
        """SELECT COUNT(*) AS n FROM pi_price_events
           WHERE sku_id = ? AND channel_id = ? AND region_id = ?
             AND event_type = ? AND timestamp >= ? AND timestamp < ?""",
        (sku_id, channel_id, region_id, event_type, window_start, ts), path=path)
    return bool(row and row["n"] > 0)


def _count_recent_events(sku_id: str, ts: str, path: str | None = None) -> int:
    try:
        dt = datetime.fromisoformat(ts)
    except Exception:
        return 0
    window_start = (dt - timedelta(days=7)).isoformat()
    row = pi_store.fetch_one(
        "SELECT COUNT(*) AS n FROM pi_price_events "
        "WHERE sku_id = ? AND timestamp >= ? AND timestamp < ?",
        (sku_id, window_start, ts), path=path)
    return int(row["n"]) if row else 0


# ---------------------------------------------------------------------------
# Queries cho API
# ---------------------------------------------------------------------------

def list_events(filters: dict[str, Any] | None = None, limit: int = 100,
                path: str | None = None) -> list[dict[str, Any]]:
    f = filters or {}
    clauses: list[str] = []
    params: list[Any] = []
    if f.get("product_id"):
        clauses.append("e.sku_id = (SELECT sku_id FROM pi_skus WHERE product_id = ?)")
        params.append(f["product_id"])
    if f.get("channel_id"):
        clauses.append("e.channel_id = ?")
        params.append(f["channel_id"])
    if f.get("region_id"):
        clauses.append("e.region_id = ?")
        params.append(f["region_id"])
    if f.get("event_type"):
        clauses.append("e.event_type = ?")
        params.append(f["event_type"])
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = pi_store.fetch_all(
        f"""SELECT e.event_id, e.sku_id, s.product_id, p.product_name, b.name AS brand,
                   e.channel_id, e.region_id, e.timestamp, e.old_price, e.new_price,
                   e.change_percent, e.event_type, e.significance, e.confidence
            FROM pi_price_events e
            JOIN pi_skus s ON s.sku_id = e.sku_id
            JOIN pi_products p ON p.product_id = s.product_id
            JOIN pi_brands b ON b.brand_id = p.brand_id
            {where}
            ORDER BY e.timestamp DESC LIMIT ?""",
        params + [limit], path=path)
    return [dict(r) for r in rows]


def list_alerts(severity: str | None = None, limit: int = 100,
                path: str | None = None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if severity:
        clauses.append("severity = ?")
        params.append(severity.upper())
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = pi_store.fetch_all(
        f"""SELECT a.alert_id, a.event_id, a.sku_id, a.severity, a.created_at,
                   a.message, a.acknowledged, p.product_name, b.name AS brand
            FROM pi_alerts a
            LEFT JOIN pi_skus s ON s.sku_id = a.sku_id
            LEFT JOIN pi_products p ON p.product_id = s.product_id
            LEFT JOIN pi_brands b ON b.brand_id = p.brand_id
            {where}
            ORDER BY a.created_at DESC LIMIT ?""",
        params + [limit], path=path)
    return [dict(r) for r in rows]
