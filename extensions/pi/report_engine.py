"""report_engine.py — Daily Intelligence Report ("Context Once — Delta Every Day").

Mô hình: mỗi chủ đề (pi_topics) là một Intelligence Event có trạng thái/vòng đời.
Daily Report chỉ lấy phần Delta của ngày:
    🆕 NEW       → topic first_seen hôm nay → giải thích đủ (What/Where/Why/Impact)
    🔄 CHANGED   → topic đã biết, có cập nhật hôm nay → chỉ báo cáo Delta
    📌 ONGOING   → topic OPEN không đổi hôm nay → 1 dòng trong Watchlist
    ➡️ UNCHANGED → topic RESOLVED → không lặp lại

Renderer trả dict payload (API) + text markdown (Telegram/Discord). Dữ liệu
nguồn: pi_topics (derived từ pi_price_events) + pi_promotions cho signal.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from extensions.pi import pi_store
from extensions.pi.models import Severity, now_iso

log = logging.getLogger("hmip.report")

_SEV_EMOJI = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢", "INFO": "⚪"}
_IMPACT = {"CRITICAL": "🔴 High", "HIGH": "🟠 Medium", "MEDIUM": "🟢 Low", "LOW": "🟢 Low"}
_SEV_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}

_EVENT_VI = {
    "PRICE_INCREASE": "giá tăng",
    "PRICE_DECREASE": "giá giảm",
    "PROMOTION_STARTED": "khuyến mãi bắt đầu",
    "PROMOTION_ENDED": "khuyến mãi kết thúc",
    "COMPETITOR_UNDERCUT": "đối thủ rẻ hơn",
    "PRICE_VOLATILITY": "giá biến động",
    "AVAILABILITY_ANOMALY": "bất thường tồn kho",
}


def _sev_emoji(sev: str | None) -> str:
    return _SEV_EMOJI.get(sev or "LOW", "🟢")


def _event_label(t: dict[str, Any]) -> str:
    raw = t.get("event_type")
    if isinstance(raw, str) and raw:
        return _EVENT_VI.get(raw, raw)
    return "thay đổi"


def _impact(t: dict[str, Any]) -> str:
    sev = t.get("severity")
    return _IMPACT.get(sev if isinstance(sev, str) else "LOW", "🟢 Low")


def _pct(v: float | None) -> str:
    return f"{v:+.2f}%" if v is not None else "—"


def _vnd(v: float | None) -> str:
    return f"{v:,.0f}₫" if v is not None else "—"


def _day(ts: str | None) -> str:
    return (ts or "")[:10]


def _sort_topics(topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(topics,
                  key=lambda t: (-_SEV_RANK.get(t.get("severity") or "LOW", 1),
                                 -(abs(t.get("last_change_pct") or 0))))


def build_daily_report(report_date: str | None = None,
                       path: str | None = None) -> dict[str, Any]:
    """Build payload đủ 7 section. report_date = 'YYYY-MM-DD' (mặc định hôm nay UTC).

    Phân loại theo events của NGÀY REPORT (không theo last_updated hiện tại)
    nên đúng cho cả báo cáo ngày hiện tại lẫn backfill ngày quá khứ:
    topic có event trong ngày → NEW (first_seen = ngày đó) hoặc CHANGED.
    Mỗi topic được enrich today_old_price/today_new_price/today_change_pct
    tính từ event đầu → cuối của ngày.
    """
    if report_date is None:
        report_date = now_iso()[:10]
    pi_store.rebuild_topics(path=path)
    all_topics = pi_store.list_topics(path=path, limit=1000)
    by_key = {t["topic_key"]: t for t in all_topics}

    day_events = pi_store.fetch_all(
        """SELECT event_id, sku_id, channel_id, region_id, timestamp, old_price,
                  new_price, change_percent, event_type
           FROM pi_price_events WHERE substr(timestamp, 1, 10) = ?
           ORDER BY timestamp, event_id""",
        (report_date,), path=path)
    per_topic: dict[str, dict[str, Any]] = {}
    for e in day_events:
        key = "|".join(str(e.get(k) or "")
                       for k in ("sku_id", "channel_id", "region_id", "event_type"))
        d = per_topic.setdefault(key, {"first": e, "last": e, "n": 0})
        d["last"] = e
        d["n"] += 1

    changed_today: list[dict[str, Any]] = []
    for key, d in per_topic.items():
        t = by_key.get(key)
        if not t:
            continue
        t = dict(t)
        t["today_old_price"] = d["first"]["old_price"]
        t["today_new_price"] = d["last"]["new_price"]
        if d["first"]["old_price"]:
            t["today_change_pct"] = round(
                (d["last"]["new_price"] - d["first"]["old_price"])
                / d["first"]["old_price"] * 100.0, 2)
        t["today_events"] = d["n"]
        changed_today.append(t)

    new_topics = _sort_topics([t for t in changed_today if _day(t["first_seen"]) == report_date])
    changed = _sort_topics([t for t in changed_today if _day(t["first_seen"]) != report_date])
    changed_keys = {t["topic_key"] for t in changed_today}
    watchlist = _sort_topics([t for t in all_topics
                              if t["status"] == "OPEN" and t["topic_key"] not in changed_keys])

    critical = [t for t in changed_today if t.get("severity") == Severity.CRITICAL.value]
    important = [t for t in changed_today
                 if t.get("severity") in (Severity.HIGH.value, Severity.MEDIUM.value)]

    # Overall status: 🔴 có CRITICAL / 🟠 có HIGH+ / 🟢 bình thường
    if critical:
        overall = "CRITICAL"
    elif any(t.get("severity") in (Severity.HIGH.value, Severity.MEDIUM.value)
             for t in changed_today):
        overall = "ATTENTION"
    else:
        overall = "NORMAL"

    actions = _build_actions(critical, important, watchlist)
    signals = _build_signals(changed_today, report_date, path)

    return {
        "report_date": report_date,
        "generated_at": now_iso(),
        "overall_status": overall,
        "summary": {
            "critical": len(critical),
            "important": len(important),
            "new_topics": len(new_topics),
            "changed_topics": len(changed),
            "watchlist": len(watchlist),
        },
        "actions": actions,
        "new_topics": new_topics,
        "changed_topics": changed,
        "watchlist": watchlist,
        "signals": signals,
        "top_critical": critical[:5],
        "top_important": _sort_topics(important)[:5],
    }


def _build_actions(critical: list[dict[str, Any]], important: list[dict[str, Any]],
                   watchlist: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """P1 = CRITICAL hôm nay; P2 = HIGH/MEDIUM hôm nay; P3 = topic đang mở."""
    return {
        "immediate": critical[:5],
        "today": _sort_topics(important)[:5],
        "monitor": watchlist[:5],
    }


def _build_signals(changed_today: list[dict[str, Any]], report_date: str,
                   path: str | None) -> list[dict[str, Any]]:
    """Key Market Signals: Pricing (từ topic hôm nay) + Promotion (promo mới bắt đầu)."""
    signals: list[dict[str, Any]] = []
    if changed_today:
        ups = [t for t in changed_today if (t.get("last_change_pct") or 0) > 0]
        downs = [t for t in changed_today if (t.get("last_change_pct") or 0) < 0]
        avg = sum(abs(t.get("last_change_pct") or 0) for t in changed_today) / len(changed_today)
        direction = "↑" if len(ups) >= len(downs) else "↓"
        hi_sig = any(t.get("significance") == "HIGH" for t in changed_today)
        confidence = "High" if hi_sig else "Medium"
        signals.append({
            "signal": "Pricing",
            "current": f"{len(changed_today)} biến động",
            "change": f"{avg:.1f}% TB",
            "direction": direction,
            "confidence": confidence,
        })
    promo = pi_store.fetch_all(
        """SELECT COUNT(*) AS n FROM pi_promotions WHERE start_time >= ?""",
        (report_date,), path=path)
    n_promo = int(promo[0]["n"]) if promo else 0
    if n_promo:
        signals.append({
            "signal": "Promotion",
            "current": f"{n_promo} KM mới",
            "change": "mới bắt đầu",
            "direction": "↑",
            "confidence": "High",
        })
    return signals


# ---------------------------------------------------------------------------
# Renderer — markdown 7 section (Telegram/Discord)
# ---------------------------------------------------------------------------

def render_markdown(report: dict[str, Any]) -> str:
    """Render report payload → text theo template chuẩn 7-section."""
    date = _fmt_date(report["report_date"])
    overall = {"CRITICAL": "🔴 Critical", "ATTENTION": "🟠 Attention",
               "NORMAL": "🟢 Normal"}.get(report["overall_status"], "⚪ —")
    s = report["summary"]
    lines: list[str] = [
        f"*DAILY FMCG INTELLIGENCE REPORT — {date}*",
        f"Reporting period: 24h • Overall status: {overall}",
        "",
        "*1️⃣ EXECUTIVE SUMMARY*",
        f"🔴 Critical: {s['critical']} • 🟠 Important: {s['important']} • "
        f"🆕 New: {s['new_topics']} • 🔄 Changed: {s['changed_topics']}",
    ]
    for t in report["top_critical"]:
        lines.append(f"🔴 {_topic_name(t)} — {_pct(_day_change(t))} "
                     f"({_vnd(_day_old(t))} → {_vnd(_day_new(t))})")
    for t in report["top_important"]:
        lines.append(f"🟠 {_topic_name(t)} — {_pct(_day_change(t))}")
    lines.append("")

    # 2. NEW TODAY
    lines.append("*2️⃣ 🆕 NEW TODAY*")
    if report["new_topics"]:
        for t in report["new_topics"]:
            lines.append(_render_new_topic(t))
    else:
        lines.append("Không có thông tin mới hôm nay.")
    lines.append("")

    # 3. CHANGED SINCE LAST REPORT
    lines.append("*3️⃣ 🔄 CHANGED SINCE LAST REPORT*")
    if report["changed_topics"]:
        for t in report["changed_topics"]:
            lines.append(_render_changed_topic(t))
    else:
        lines.append("Không có thay đổi nào trên các vấn đề đang theo dõi.")
    lines.append("")

    # 4. ONGOING WATCHLIST
    lines.append("*4️⃣ 📌 ONGOING WATCHLIST*")
    if report["watchlist"]:
        for t in report["watchlist"][:8]:
            status = "Monitoring" if t["status"] == "OPEN" else "Stable"
            lines.append(f"• {_topic_name(t)} — {status} "
                         f"({t.get('event_count', 1)} lần cập nhật, "
                         f"tổng {_pct(t.get('total_change_pct'))})")
    else:
        lines.append("Watchlist trống.")
    lines.append("")

    # 5. RECOMMENDED ACTIONS
    a = report["actions"]
    lines.append("*5️⃣ 🎯 RECOMMENDED ACTIONS*")
    if a["immediate"]:
        lines.append("P1 — Immediate:")
        for t in a["immediate"]:
            lines.append(f"• Rà soát {_topic_name(t)} ({_pct(t.get('last_change_pct'))})")
    if a["today"]:
        lines.append("P2 — Today:")
        for t in a["today"]:
            lines.append(f"• Xem lại {_topic_name(t)} ({_pct(t.get('last_change_pct'))})")
    lines.append("P3 — Monitor:")
    for t in a["monitor"][:3]:
        lines.append(f"• {_topic_name(t)}")
    if not a["immediate"] and not a["today"]:
        lines.append("• Không có hành động khẩn — tiếp tục theo dõi thường.")
    lines.append("")

    # 6. KEY MARKET SIGNALS
    lines.append("*6️⃣ 📊 KEY MARKET SIGNALS*")
    if report["signals"]:
        for sig in report["signals"]:
            lines.append(f"• {sig['signal']}: {sig['current']} ({sig.get('change', '—')}) "
                         f"{sig.get('direction', '—')} — {sig.get('confidence', '—')}")
    else:
        lines.append("Không có signal đáng kể.")
    lines.append("")

    # 7. HISTORY & SOURCES
    lines.append("*7️⃣ 📚 HISTORY & SOURCES*")
    lines.append("Timeline & raw data: dùng endpoint /api/price-intelligence/topics "
                 "(View Timeline per topic). Nguồn: collectors Firecrawl/ScraperAPI/ZenRows/Jina.")
    return "\n".join(lines)


def _fmt_date(iso_date: str) -> str:
    """'YYYY-MM-DD' → 'DD/MM/YYYY'."""
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d")
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return iso_date


def _day_change(t: dict[str, Any]) -> float | None:
    return t.get("today_change_pct", t.get("last_change_pct"))


def _day_old(t: dict[str, Any]) -> float | None:
    return t.get("today_old_price", t.get("baseline_price"))


def _day_new(t: dict[str, Any]) -> float | None:
    return t.get("today_new_price", t.get("current_price"))


def _topic_name(t: dict[str, Any]) -> str:
    name = t.get("product_name") or t.get("sku_id") or "?"
    brand = t.get("brand")
    ch = t.get("channel_id") or ""
    reg = t.get("region_id") or ""
    place = " / ".join(x for x in (ch, reg) if x)
    base = f"{brand} {name}" if brand else name
    return f"{base} ({place})" if place else base


def _render_new_topic(t: dict[str, Any]) -> str:
    what = _event_label(t)
    return (
        f"\n🆕 *{_topic_name(t)}*\n"
        f"• What: {what} {_pct(_day_change(t))} "
        f"từ {_vnd(_day_old(t))} → {_vnd(_day_new(t))}\n"
        f"• Where: {t.get('channel_id') or '—'} / {t.get('region_id') or '—'} • "
        f"First seen: {_fmt_date(_day(t.get('first_seen')))}\n"
        f"• Why: {_sev_emoji(t.get('severity'))} {t.get('severity') or ''} • "
        f"Impact: {_impact(t)}"
    )


def _render_changed_topic(t: dict[str, Any]) -> str:
    return (
        f"\n🔄 *{_topic_name(t)}*\n"
        f"• Context: {_event_label(t)} được theo dõi từ "
        f"{_fmt_date(_day(t.get('first_seen')))} "
        f"({t.get('event_count', 1)} lần cập nhật)\n"
        f"• Today: {_vnd(_day_old(t))} → {_vnd(_day_new(t))} ({_pct(_day_change(t))})\n"
        f"• Delta tích luỹ: {_pct(t.get('total_change_pct'))} • "
        f"Impact: {_impact(t)}"
    )


# ---------------------------------------------------------------------------
# Delivery — gửi qua Telegram/Discord (best-effort)
# ---------------------------------------------------------------------------

def send_daily_report(report_date: str | None = None,
                      path: str | None = None) -> dict[str, Any]:
    """Build + render + đẩy lên Telegram/Discord + email VN/ZH + đánh dấu topic.

    Trả dict {sent: {telegram, discord, email}, text_len, report_date}.
    Kênh nào chưa cấu hình → console fallback.
    Email: extensions/pi/email_report.send_report_email — bilingual
    (vi → chubay008 + kalihello541, zh → uythanhhoang + yingxue0510),
    định tuyến qua EMAIL_VI/EMAIL_ZH; tắt bằng HMIP_EMAIL_REPORT=off.
    """
    from extensions.notifiers import discord as dc
    from extensions.notifiers import telegram as tg

    report = build_daily_report(report_date, path=path)
    text = render_markdown(report)
    sent_tg = tg.send_text(text)
    sent_dc = dc.send_text(text)
    sent_email: dict[str, bool] = {}
    from extensions.pi import email_report
    if email_report.email_report_enabled():
        sent_email = email_report.send_report_email(report)
        log.info("Daily report email → %s", sent_email)

    keys = [t["topic_key"] for t in (report["new_topics"] + report["changed_topics"])]
    email_ok = any(sent_email.values()) if sent_email else False
    sent_any = sent_tg or sent_dc or email_ok
    if sent_any:
        pi_store.mark_topics_reported(keys, report["report_date"], path=path)
    return {"sent": {"telegram": sent_tg, "discord": sent_dc, "email": sent_email},
            "text_len": len(text), "report_date": report["report_date"],
            "topics_reported": len(keys) if sent_any else 0}
