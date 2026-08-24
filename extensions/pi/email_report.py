"""email_report.py — Daily Intelligence Report qua Email (Gmail SMTP, bilingual).

Theo mẫu beer-scan `send_email.py`: hai nhóm người nhận cố định
(vi → ZH) với subject + HTML body render từ payload `build_daily_report`.
Env (xem .env.example):
    SMTP_HOST (default smtp.gmail.com), SMTP_PORT (default 465, SSL),
    SMTP_USER (default chubay008@gmail.com), SMTP_APP_PASS (app password),
    HMIP_EMAIL_REPORT ("on" default; "off" để tắt), và danh sách người
    nhận có thể ghi đè EMAIL_VI / EMAIL_ZH (comma-separated).

Chỉ ghi log console khi chưa cấu hình SMTP (như các notifier khác).
"""

from __future__ import annotations

import html
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from extensions.pi.report_engine import (
    _fmt_date,
    _impact,
    _pct,
    _sev_emoji,
    _topic_name,
    _vnd,
)

log = logging.getLogger("hmip.email_report")

_VI = ["chubay008@gmail.com", "kalihello541@gmail.com"]
_ZH = ["uythanhhoang@gmail.com"]  # yingxue0510 tạm thời gỡ (28/08) — có thể thêm lại bất cứ lúc nào

_L: dict[str, dict[str, str]] = {
    "vi": {
        "title": "BÁO CÁO TIN TỨC FMCG HÀNG NGÀY — {date}",
        "period": "Kỳ báo cáo: 24h • Trạng thái tổng: {overall}",
        "s1": "1️⃣ TÓM TẮT ĐIỀU HÀNH",
        "s2": "2️⃣ 🆕 MỚI HÔM NAY",
        "s3": "3️⃣ 🔄 THAY ĐỔI SO VỚI LẦN BÁO TRƯỚC",
        "s4": "4️⃣ 📌 DANH SÁCH THEO DÕI",
        "s5": "5️⃣ 🎯 HÀNH ĐỘNG KHUYẾN NGHỊ",
        "s6": "6️⃣ 📊 TÍN HIỆU THỊ TRƯỜNG CHÍNH",
        "s7": "7️⃣ 📚 LỊCH SỬ & NGUỒN",
        "critical": "nghiêm trọng", "important": "quan trọng",
        "new": "mới", "changed": "thay đổi", "watchlist": "đang theo dõi",
        "no_new": "Không có thông tin mới hôm nay.",
        "no_changed": "Không có thay đổi nào trên các vấn đề đang theo dõi.",
        "no_watch": "Watchlist trống.",
        "watch_status": "Đang theo dõi", "watch_stable": "Ổn định",
        "p1": "P1 — Ngay:", "p2": "P2 — Hôm nay:", "p3": "P3 — Theo dõi:",
        "p1_do": "Rà soát", "p2_do": "Xem lại",
        "no_action": "• Không có hành động khẩn — tiếp tục theo dõi thường.",
        "no_signal": "Không có signal đáng kể.",
        "history_txt": ("Timeline & raw data: dùng endpoint /api/price-intelligence/topics "
                        "(View Timeline per topic). Nguồn: collectors Firecrawl/ScraperAPI/"
                        "ZenRows/Jina."),
        "today": "Hôm nay", "cumulative": "Delta tích luỹ", "impact": "Impact",
        "what": "What", "where": "Where", "first_seen": "First seen",
        "why": "Why", "from": "từ", "updates": "lần cập nhật",
        "tracked_since": "Theo dõi từ", "total": "tổng",
    },
    "zh": {
        "title": "每日快消品情报报告 — {date}",
        "period": "报告周期: 24h • 总体状态: {overall}",
        "s1": "1️⃣ 执行摘要",
        "s2": "2️⃣ 🆕 今日新增",
        "s3": "3️⃣ 🔄 自上次报告以来的变化",
        "s4": "4️⃣ 📌 持续观察名单",
        "s5": "5️⃣ 🎯 建议行动",
        "s6": "6️⃣ 📊 关键市场信号",
        "s7": "7️⃣ 📚 历史与来源",
        "critical": "严重", "important": "重要",
        "new": "新增", "changed": "变化", "watchlist": "观察中",
        "no_new": "今天没有新增信息。",
        "no_changed": "所跟踪议题今天无变化。",
        "no_watch": "观察名单为空。",
        "watch_status": "观察中", "watch_stable": "稳定",
        "p1": "P1 — 立即:", "p2": "P2 — 今天:", "p3": "P3 — 关注:",
        "p1_do": "核查", "p2_do": "复查",
        "no_action": "• 无紧急行动——继续常规跟踪。",
        "no_signal": "无显著信号。",
        "history_txt": ("时间线与原始数据：使用 /api/price-intelligence/topics "
                        "端点（每个议题的 View Timeline）。"
                        "来源：Firecrawl/ScraperAPI/ZenRows/Jina 采集器。"),
        "today": "今日", "cumulative": "累积变化", "impact": "影响",
        "what": "事件", "where": "渠道/区域", "first_seen": "首次发现",
        "why": "原因", "from": "从", "updates": "次更新",
        "tracked_since": "跟踪自", "total": "总计",
    },
}


def _l(lang: str, key: str) -> str:
    return _L[lang][key]


def render_html(report: dict[str, Any], lang: str = "vi") -> tuple[str, str]:
    """Render payload → (subject, html body) theo `lang`."""
    date = _fmt_date(report["report_date"])
    overall_map = {"CRITICAL": _l(lang, "critical"),
                   "ATTENTION": _l(lang, "important"),
                   "NORMAL": "Normal"}
    overall = overall_map.get(report["overall_status"], "Normal")
    if lang == "vi" and report["overall_status"] == "NORMAL":
        overall = "Normal"
    emoji = {"CRITICAL": "🔴", "ATTENTION": "🟠", "NORMAL": "🟢"}.get(
        report["overall_status"], "⚪")

    s = report["summary"]
    parts: list[str] = [
        "<html><body style=\"font-family:Arial,sans-serif;max-width:720px;margin:0 auto\">",
        f"<h2 style=\"color:#1a3c6e\">{_l(lang, 'title').format(date=html.escape(date))}</h2>",
        f"<p style=\"color:#666\">{_l(lang, 'period').format(overall=overall)}</p>",
        f"<h3>{_l(lang, 's1')}</h3>",
        f"<p>{emoji} "
        f"🔴 {_l(lang, 'critical')}: {s['critical']} • "
        f"🟠 {_l(lang, 'important')}: {s['important']} • "
        f"🆕 {_l(lang, 'new')}: {s['new_topics']} • "
        f"🔄 {_l(lang, 'changed')}: {s['changed_topics']}</p>",
    ]

    for t in report["top_critical"]:
        parts.append(f"<p>🔴 <b>{html.escape(_topic_name(t))}</b> — {_pct(_day_change(t))} "
                     f"({_vnd(_day_old(t))} → {_vnd(_day_new(t))})</p>")
    for t in report["top_important"]:
        parts.append(f"<p>🟠 <b>{html.escape(_topic_name(t))}</b> — {_pct(_day_change(t))}</p>")

    parts.append(f"<h3>{_l(lang, 's2')}</h3>")
    if report["new_topics"]:
        for t in report["new_topics"]:
            parts.append(
                f"<p>🆕 <b>{html.escape(_topic_name(t))}</b><br>"
                f"• {_l(lang,'what')}: {_pct(_day_change(t))} {_l(lang,'from')} "
                f"{_vnd(_day_old(t))} → {_vnd(_day_new(t))}<br>"
                f"• {_l(lang,'where')}: {html.escape(t.get('channel_id') or '—')} / "
                f"{html.escape(t.get('region_id') or '—')} • "
                f"{_l(lang,'first_seen')}: {html.escape(_fmt_date(_day(t.get('first_seen'))))}<br>"
                f"• {_l(lang,'why')}: {_sev_emoji(t.get('severity'))} {t.get('severity') or ''} • "
                f"{_l(lang,'impact')}: {_impact(t)}</p>")
    else:
        parts.append(f"<p>{_l(lang, 'no_new')}</p>")

    parts.append(f"<h3>{_l(lang, 's3')}</h3>")
    if report["changed_topics"]:
        for t in report["changed_topics"]:
            parts.append(
                f"<p>🔄 <b>{html.escape(_topic_name(t))}</b><br>"
                f"• {_l(lang,'tracked_since')}: "
                f"{html.escape(_fmt_date(_day(t.get('first_seen'))))} "
                f"({t.get('event_count', 1)} {_l(lang,'updates')})<br>"
                f"• {_l(lang,'today')}: {_vnd(_day_old(t))} → {_vnd(_day_new(t))} "
                f"({_pct(_day_change(t))})<br>"
                f"• {_l(lang,'cumulative')}: {_pct(t.get('total_change_pct'))} • "
                f"{_l(lang,'impact')}: {_impact(t)}</p>")
    else:
        parts.append(f"<p>{_l(lang, 'no_changed')}</p>")

    parts.append(f"<h3>{_l(lang, 's4')}</h3>")
    if report["watchlist"]:
        for t in report["watchlist"][:8]:
            status = _l(lang, "watch_status") if t["status"] == "OPEN" else _l(lang, "watch_stable")
            parts.append(
                f"<p>• {html.escape(_topic_name(t))} — {status} "
                f"({t.get('event_count', 1)} {_l(lang, 'updates')}, "
                f"{_l(lang, 'total')} {_pct(t.get('total_change_pct'))})</p>")
    else:
        parts.append(f"<p>{_l(lang, 'no_watch')}</p>")

    a = report["actions"]
    parts.append(f"<h3>{_l(lang, 's5')}</h3>")
    if a["immediate"]:
        parts.append(f"<p><b>{_l(lang, 'p1')}</b></p><ul>")
        for t in a["immediate"]:
            parts.append(f"<li>{_l(lang,'p1_do')} {html.escape(_topic_name(t))} "
                         f"({_pct(t.get('last_change_pct'))})</li>")
        parts.append("</ul>")
    if a["today"]:
        parts.append(f"<p><b>{_l(lang, 'p2')}</b></p><ul>")
        for t in a["today"]:
            parts.append(f"<li>{_l(lang,'p2_do')} {html.escape(_topic_name(t))} "
                         f"({_pct(t.get('last_change_pct'))})</li>")
        parts.append("</ul>")
    parts.append(f"<p><b>{_l(lang, 'p3')}</b></p><ul>")
    for t in a["monitor"][:3]:
        parts.append(f"<li>{html.escape(_topic_name(t))}</li>")
    parts.append("</ul>")
    if not a["immediate"] and not a["today"]:
        parts.append(f"<p>{_l(lang, 'no_action')}</p>")

    parts.append(f"<h3>{_l(lang, 's6')}</h3>")
    if report["signals"]:
        for sig in report["signals"]:
            change = html.escape(sig.get("change", "—"))
            conf = html.escape(sig.get("confidence", "—"))
            parts.append(f"<p>• <b>{html.escape(sig['signal'])}</b>: "
                         f"{html.escape(sig['current'])} ({change}) "
                         f"{sig.get('direction', '—')} — {conf}</p>")
    else:
        parts.append(f"<p>{_l(lang, 'no_signal')}</p>")

    parts.append(f"<h3>{_l(lang, 's7')}</h3>")
    parts.append(f"<p style=\"color:#666\">{_l(lang, 'history_txt')}</p>")
    parts.append("</body></html>")

    subject = (f"DAILY FMCG INTELLIGENCE REPORT — {date}" if lang == "vi"
               else f"每日快消品情报报告 — {date}")
    return subject, "\n".join(parts)


def _day(d: dict[str, Any] | str | None) -> str:
    if isinstance(d, dict):
        d = d.get("first_seen") or ""
    return (d or "")[:10]


def _day_change(t: dict[str, Any]) -> float | None:
    return t.get("today_change_pct", t.get("last_change_pct"))


def _day_old(t: dict[str, Any]) -> float | None:
    return t.get("today_old_price", t.get("baseline_price"))


def _day_new(t: dict[str, Any]) -> float | None:
    return t.get("today_new_price", t.get("current_price"))


def _recipients(lang: str) -> list[str]:
    env = os.getenv(f"EMAIL_{lang.upper()}", "").strip()
    if env:
        return [e.strip() for e in env.split(",") if e.strip()]
    return _VI if lang == "vi" else _ZH


def _smtp_config() -> tuple[str, int, str, str]:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER", "chubay008@gmail.com").strip()
    password = os.getenv("SMTP_APP_PASS", "").strip()
    return host, port, user, password


def send_via_smtp(subject: str, html_body: str, to_addrs: list[str],
                  *, timeout: float = 30.0) -> bool:
    """Gửi 1 email qua Gmail SMTP (SSL 465 mặc định). True khi gửi được."""
    host, port, user, password = _smtp_config()
    if not user or not password:
        log.info("[email no-report] subject=%r to=%s (chưa set SMTP_APP_PASS)",
                 subject, ", ".join(to_addrs))
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx) as server:
            server.login(user, password)
            server.sendmail(user, to_addrs, msg.as_string())
        log.info("[email sent] subject=%r → %s", subject, ", ".join(to_addrs))
        return True
    except smtplib.SMTPException as exc:  # auth/send fail cũng best-effort, log thôi
        log.warning("[email failed] %s → %s: %s", subject, ", ".join(to_addrs), exc)
        return False


def send_report_email(report: dict[str, Any]) -> dict[str, bool]:
    """Gửi bilingual: vi → chubay008 + kalihello541; zh → uythanhhoang (yingxue đã gỡ 28/08).

    Hoạn lọc qua env EMAIL_VI / EMAIL_ZH. Trả {"vi": bool, "zh": bool}.
    """
    out: dict[str, bool] = {}
    for lang in ("vi", "zh"):
        subject, body = render_html(report, lang=lang)
        out[lang] = send_via_smtp(subject, body, _recipients(lang))
    return out


def email_report_enabled() -> bool:
    return os.getenv("HMIP_EMAIL_REPORT", "on").strip().lower() not in ("off", "0", "false")
