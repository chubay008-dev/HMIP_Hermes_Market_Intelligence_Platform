"""Test cho auth middleware multi-token (extensions/auth.py)."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from extensions.api import app
from extensions import auth as auth_mod


@pytest.fixture()
def client_no_auth(monkeypatch):
    monkeypatch.delenv("HMIP_API_TOKEN", raising=False)
    monkeypatch.delenv("HMIP_API_TOKENS", raising=False)
    auth_mod.reload_tokens()
    with TestClient(app) as c:
        yield c


def test_no_auth_when_token_unset(client_no_auth):
    # dev mode: không bật auth
    assert client_no_auth.get("/api/latest").status_code == 200


def test_health_always_public(monkeypatch):
    monkeypatch.setenv("HMIP_API_TOKENS", '["tokA","tokB"]')
    auth_mod.reload_tokens()
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200


def test_protected_route_requires_valid_token(monkeypatch):
    monkeypatch.setenv("HMIP_API_TOKENS", '["tokA","tokB"]')
    auth_mod.reload_tokens()
    with TestClient(app) as c:
        # thiếu token
        assert c.get("/api/latest").status_code == 401
        # sai token
        assert c.get("/api/latest", headers={"Authorization": "Bearer wrong"}).status_code == 401
        # token A hợp lệ
        assert c.get("/api/latest", headers={"Authorization": "Bearer tokA"}).status_code == 200
        # token B hợp lệ
        assert c.get("/api/latest", headers={"Authorization": "Bearer tokB"}).status_code == 200


def test_dashboard_shell_public(monkeypatch):
    monkeypatch.setenv("HMIP_API_TOKENS", '["tokA"]')
    auth_mod.reload_tokens()
    with TestClient(app) as c:
        # '/' được phép truy cập không token (UI tự login)
        assert c.get("/").status_code == 200


def test_backward_compat_single_token(monkeypatch):
    # Chỉ HMIP_API_TOKEN cũ (chuỗi đơn) vẫn hoạt động
    monkeypatch.delenv("HMIP_API_TOKENS", raising=False)
    monkeypatch.setenv("HMIP_API_TOKEN", "legacy")
    auth_mod.reload_tokens()
    with TestClient(app) as c:
        assert c.get("/api/latest").status_code == 401
        assert c.get("/api/latest", headers={"Authorization": "Bearer legacy"}).status_code == 200


def test_malformed_tokens_env_falls_back(monkeypatch):
    # JSON hỏng → coi như không có token (dev mode mở)
    monkeypatch.setenv("HMIP_API_TOKENS", "not-json[")
    auth_mod.reload_tokens()
    assert auth_mod.is_enabled() is False
    with TestClient(app) as c:
        assert c.get("/api/latest").status_code == 200


def test_is_enabled_reflects_env(monkeypatch):
    monkeypatch.setenv("HMIP_API_TOKENS", '["x"]')
    importlib.reload(auth_mod)
    try:
        assert auth_mod.is_enabled() is True
    finally:
        importlib.reload(auth_mod)
