"""Test cho auto-scan scheduler và Telegram notifier."""

from __future__ import annotations

import tempfile
import os

import pytest

from extensions.notifiers.telegram import _format, is_configured, notify
from extensions.scheduler import scan_once
from extensions.api import app


@pytest.fixture()
def temp_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr("extensions.db.DEFAULT_DB_PATH", path)
    monkeypatch.setenv("HMIP_DB_PATH", path)
    yield path
    os.unlink(path)


# ----------------------------------------------------------- notifier

def test_format_contains_key_fields():
    msg = _format("ESCALATE", "Saigon", 20083.0, 11.57, 18000.0)
    assert "ESCALATE" in msg
    assert "Saigon" in msg
    assert "20,083" in msg           # định dạng tiếng Việt có dấu phẩy
    assert "+11.57%" in msg


def test_notify_fallback_when_unconfigured(temp_db, monkeypatch):
    monkeypatch.setattr("extensions.notifiers.telegram.TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr("extensions.notifiers.telegram.TELEGRAM_CHAT_ID", "")
    assert is_configured() is False
    assert notify("ALERT", "X", 100.0, 5.1, 95.0) is True


def test_notify_graceful_on_bad_token(temp_db, monkeypatch):
    monkeypatch.setattr("extensions.notifiers.telegram.TELEGRAM_BOT_TOKEN", "bad-token-xyz")
    monkeypatch.setattr("extensions.notifiers.telegram.TELEGRAM_CHAT_ID", "12345")
    assert is_configured() is True
    assert notify("ALERT", "X", 100.0, 5.1, 95.0) is False


# ----------------------------------------------------------- scheduler

def test_scan_once_runs_and_persists(temp_db, monkeypatch):
    monkeypatch.setattr("extensions.db.DEFAULT_DB_PATH", temp_db)
    counts = scan_once()
    assert counts["scanned"] == 2
    assert counts["errors"] == 0
    from extensions import db
    total = sum(len(db.get_history(pid, path=temp_db)) for pid in ("P123", "P456"))
    assert total >= 2


# ------------------------------------------------------- api autoscan

def test_autoscan_lifecycle(temp_db, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.delenv("HMIP_API_TOKEN", raising=False)
    monkeypatch.setattr("extensions.db.DEFAULT_DB_PATH", temp_db)
    client = TestClient(app)

    assert client.get("/api/autoscan/status").json()["running"] is False

    start = client.post("/api/autoscan/start")
    assert start.status_code == 200
    assert start.json()["status"] == "started"

    import time
    time.sleep(6)
    assert client.get("/api/autoscan/status").json()["running"] is True
    assert len(client.get("/api/latest").json()) >= 1

    stop = client.post("/api/autoscan/stop")
    assert stop.status_code == 200
    assert client.get("/api/autoscan/status").json()["running"] is False


def test_health_reports_autoscan_and_telegram(temp_db, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr("extensions.db.DEFAULT_DB_PATH", temp_db)
    monkeypatch.setattr("extensions.notifiers.telegram.TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr("extensions.notifiers.telegram.TELEGRAM_CHAT_ID", "")
    h = TestClient(app).get("/api/health").json()
    assert "auto_scan" in h
    assert h["telegram"] is False
