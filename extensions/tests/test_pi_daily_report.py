"""test_pi_daily_report.py — Kiểm thử Daily Intelligence Report Engine.

Mô hình "Context Once — Delta Every Day": topic (pi_topics) có vòng đời
(first_seen/last_updated/status), Daily Report chỉ lấy Delta của ngày:
NEW (first_seen hôm nay) / CHANGED (đã biết, cập nhật hôm nay) / WATCHLIST.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from extensions.pi import events, pi_store, report_engine, seed, service

PI_DB = str(Path(tempfile.gettempdir()) / "hmip_pi_daily_report_test.db")


@pytest.fixture(scope="module")
def db():
    if Path(PI_DB).exists():
        Path(PI_DB).unlink()
    seed.seed_full(history_days=20, path=PI_DB, seed=42)
    events.detect_events(path=PI_DB)
    return PI_DB


@pytest.fixture(autouse=True)
def _no_real_email(monkeypatch):
    """TUYỆT ĐỐI không gửi email thật từ test (env CI có SMTP_APP_PASS thật).

    Test email bật lại bằng monkeypatch.setenv('HMIP_EMAIL_REPORT', 'on')
    + mock smtplib.SMTP_SSL.
    """
    monkeypatch.setenv("HMIP_EMAIL_REPORT", "off")


def _busiest_day(db: str) -> str:
    row = pi_store.fetch_one(
        "SELECT substr(timestamp,1,10) AS d, COUNT(*) AS n FROM pi_price_events "
        "GROUP BY d ORDER BY n DESC LIMIT 1", path=db)
    assert row and row["n"] > 0
    return row["d"]


def test_topics_schema(db):
    row = pi_store.fetch_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pi_topics'", path=db)
    assert row, "missing table pi_topics"


def test_topics_synced_from_events(db):
    n = pi_store.rebuild_topics(path=db)
    assert n > 0
    assert pi_store.count_rows("pi_topics", path=db) == n
    topics = pi_store.list_topics(path=db)
    for t in topics:
        assert t["first_seen"] and t["last_updated"] and t["status"] in ("OPEN", "RESOLVED")
        assert t["first_seen"] <= t["last_updated"]
        assert t["event_count"] >= 1


def test_rebuild_topics_idempotent_and_preserves_reported(db):
    topics = pi_store.list_topics(limit=3, path=db)
    keys = [t["topic_key"] for t in topics]
    pi_store.mark_topics_reported(keys, "2026-08-22", path=db)
    n1 = pi_store.rebuild_topics(path=db)
    n2 = pi_store.rebuild_topics(path=db)
    assert n1 == n2
    row = pi_store.fetch_one(
        "SELECT last_reported_at FROM pi_topics WHERE topic_key = ?", (keys[0],), path=db)
    assert row and row["last_reported_at"] == "2026-08-22"


def test_build_daily_report_classifies_new_and_changed(db):
    day = _busiest_day(db)
    rep = report_engine.build_daily_report(report_date=day, path=db)
    assert rep["report_date"] == day
    assert rep["overall_status"] in ("NORMAL", "ATTENTION", "CRITICAL")
    s = rep["summary"]
    assert s["new_topics"] + s["changed_topics"] > 0
    # NEW = first_seen đúng ngày report; CHANGED = đã tồn tại trước đó
    for t in rep["new_topics"]:
        assert t["first_seen"][:10] == day
    for t in rep["changed_topics"]:
        assert t["first_seen"][:10] != day


def test_report_delta_enriched_from_day_events(db):
    day = _busiest_day(db)
    rep = report_engine.build_daily_report(report_date=day, path=db)
    topics = rep["new_topics"] + rep["changed_topics"]
    assert topics
    for t in topics:
        assert "today_old_price" in t and "today_new_price" in t
    # thứ tự: CRITICAL trước
    sev_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
    ranks = [sev_rank.get(t.get("severity"), 0) for t in topics]
    assert ranks == sorted(ranks, reverse=True)


def test_render_markdown_sections(db):
    day = _busiest_day(db)
    text = service.daily_report_text(report_date=day, path=db)
    for section in ("EXECUTIVE SUMMARY", "NEW TODAY", "CHANGED SINCE LAST REPORT",
                    "ONGOING WATCHLIST", "RECOMMENDED ACTIONS", "KEY MARKET SIGNALS",
                    "HISTORY & SOURCES"):
        assert section in text
    assert "Reporting period: 24h" in text


def test_report_no_events_day_is_calm(db):
    rep = report_engine.build_daily_report(report_date="1999-01-01", path=db)
    assert rep["overall_status"] == "NORMAL"
    assert rep["summary"]["new_topics"] == 0
    assert rep["summary"]["changed_topics"] == 0
    text = report_engine.render_markdown(rep)
    assert "Không có thông tin mới" in text


def test_topic_timeline(db):
    topics = pi_store.list_topics(limit=1, path=db)
    key = topics[0]["topic_key"]
    tl = service.topic_timeline(key, path=db)
    assert len(tl) >= 1
    assert tl[0]["event_id"] == topics[0]["last_event_id"] or len(tl) == topics[0]["event_count"]
    assert service.topic_timeline("bad|key", path=db) == []


def test_send_daily_report_marks_topics(db):
    day = _busiest_day(db)
    res = report_engine.send_daily_report(report_date=day, path=db)
    assert res["sent"]["telegram"] and res["sent"]["discord"]  # console fallback
    assert res["topics_reported"] > 0
    row = pi_store.fetch_one(
        "SELECT COUNT(*) AS n FROM pi_topics WHERE last_reported_at = ?", (day,), path=db)
    assert row["n"] == res["topics_reported"]

# ---------------------------------------------------------------------------
# Email channel (PR: vi + zh qua Gmail SMTP) — mock SMTP để không gọi mạng.
# ---------------------------------------------------------------------------

def test_email_render_html_vi_and_zh(db):
    from extensions.pi import email_report
    day = _busiest_day(db)
    report = report_engine.build_daily_report(report_date=day, path=db)
    for lang, must_have in (
        ("vi", ("BÁO CÁO TIN TỨC FMCG HÀNG NGÀY", "TÓM TẮT ĐIỀU HÀNH",
                "MỚI HÔM NAY", "THAY ĐỔI", "LỊCH SỬ", "DAILY FMCG INTELLIGENCE REPORT")),
        ("zh", ("每日快消品情报报告", "执行摘要", "今日新增",
                "自上次报告以来的变化", "历史与来源")),
    ):
        subject, body = email_report.render_html(report, lang=lang)
        for needle in must_have:
            assert needle in body or needle in subject, f"[{lang}] missing {needle!r}"
        assert "<html>" in body and "</html>" in body

def test_email_render_full_payload_all_branches():
    """Render không lỗi KeyError khi có đủ NEW + CHANGED + WATCHLIST (cả 2 ngôn ngữ)."""
    from extensions.pi import email_report
    topic = {
        "topic_key": "SKU1|ch1|rg1|PRICE_INCREASE", "sku_id": "SKU1",
        "product_name": "Bia Test 330ml", "brand": "TestBrand",
        "channel_id": "tiki", "region_id": "HN", "event_type": "PRICE_INCREASE",
        "severity": "HIGH", "status": "OPEN", "first_seen": "2026-08-20T03:00:00",
        "last_updated": "2026-08-24T03:00:00", "event_count": 3,
        "baseline_price": 10000.0, "current_price": 12000.0,
        "total_change_pct": 20.0, "last_change_pct": 5.0,
        "today_old_price": 11000.0, "today_new_price": 12000.0,
        "today_change_pct": 9.09, "today_events": 1,
    }
    new_topic = dict(topic, topic_key="SKU2|ch1|rg1|PRICE_DECREASE",
                     sku_id="SKU2", event_type="PRICE_DECREASE",
                     first_seen="2026-08-24T03:00:00")
    report = {
        "report_date": "2026-08-24", "generated_at": "2026-08-24T08:00:00",
        "overall_status": "ATTENTION",
        "summary": {"critical": 0, "important": 1, "new_topics": 1,
                    "changed_topics": 1, "watchlist": 1},
        "actions": {"immediate": [], "today": [topic], "monitor": [topic]},
        "new_topics": [new_topic], "changed_topics": [topic],
        "watchlist": [topic],
        "signals": [{"signal": "Pricing", "current": "2 biến động",
                     "change": "7.0% TB", "direction": "↑", "confidence": "High"}],
        "top_critical": [], "top_important": [topic],
    }
    for lang, must_have in (
        ("vi", ("MỚI HÔM NAY", "Theo dõi từ", "Delta tích luỹ", "Đang theo dõi", "tổng")),
        ("zh", ("今日新增", "跟踪自", "累积变化", "观察中", "总计")),
    ):
        subject, body = email_report.render_html(report, lang=lang)
        for needle in must_have:
            assert needle in body, f"[{lang}] missing {needle!r}"
        assert "HÔME" not in body  # không còn lỗi chính tả



def test_email_recipients_and_send_all_langs(db, monkeypatch):
    from extensions.pi import email_report
    day = _busiest_day(db)
    report = report_engine.build_daily_report(report_date=day, path=db)
    calls: list[dict] = []

    class _FakeSMTP:
        def __init__(self, host, port, timeout=30, context=None):
            calls.append({"host": host, "port": port})

        def login(self, user, password):
            calls.append({"login": user})

        def sendmail(self, frm, to, msg):
            calls.append({"send": list(to), "subject": frm})

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("smtplib.SMTP_SSL", _FakeSMTP)
    monkeypatch.setenv("SMTP_USER", "chubay008@gmail.com")
    monkeypatch.setenv("SMTP_APP_PASS", "tok")
    sent = email_report.send_report_email(report)
    assert sent == {"vi": True, "zh": True}
    tos = [c["send"] for c in calls if "send" in c]
    vi = next(t for t in tos if "chubay008@gmail.com" in t)
    zh = next(t for t in tos if "uythanhhoang@gmail.com" in t)
    assert len(vi) == 2 and "kalihello541@gmail.com" in vi
    assert len(zh) == 1  # yingxue0510 đã gỡ (28/08) — chỉ uythanhhoang


def test_email_recipients_env_override(db, monkeypatch):
    from extensions.pi import email_report
    day = _busiest_day(db)
    report = report_engine.build_daily_report(report_date=day, path=db)
    calls: list[dict] = []

    class _FakeSMTP:
        def __init__(self, host, port, timeout=30, context=None):
            pass

        def login(self, user, password):
            pass

        def sendmail(self, frm, to, msg):
            calls.append({"send": list(to)})

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("smtplib.SMTP_SSL", _FakeSMTP)
    monkeypatch.setenv("SMTP_USER", "u@x")
    monkeypatch.setenv("SMTP_APP_PASS", "p")
    monkeypatch.setenv("EMAIL_ZH", "uythanhhoang@gmail.com,yingxue0510@gmail.com")
    email_report.send_report_email(report)
    zh = next(t for t in (c["send"] for c in calls if "send" in c) if "yingxue0510@gmail.com" in t)
    assert len(zh) == 2  # override có thể thêm lại yingxue0510 khi muốn


def test_send_daily_report_includes_email(db, monkeypatch):
    captured = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=30, context=None):
            pass

        def login(self, user, password):
            pass

        def sendmail(self, frm, to, msg):
            captured.setdefault("lang", []).append((frm, list(to)))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("smtplib.SMTP_SSL", _FakeSMTP)
    monkeypatch.setenv("SMTP_USER", "u@x")
    monkeypatch.setenv("SMTP_APP_PASS", "p")
    monkeypatch.setenv("HMIP_EMAIL_REPORT", "on")  # autouse fixture tắt mặc định
    day = _busiest_day(db)
    res = report_engine.send_daily_report(report_date=day, path=db)
    assert res["sent"]["email"] == {"vi": True, "zh": True}
    assert res["sent"]["telegram"] and res["sent"]["discord"]


def test_email_disabled_env(db, monkeypatch):
    from extensions.pi import email_report
    monkeypatch.setenv("HMIP_EMAIL_REPORT", "off")
    assert email_report.email_report_enabled() is False
    monkeypatch.setenv("HMIP_EMAIL_REPORT", "on")
    assert email_report.email_report_enabled() is True

