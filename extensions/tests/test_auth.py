"""Test cho auth middleware (extensions/auth.py)."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from extensions.api import app
from extensions.auth import is_enabled


@pytest.fixture()
def client_no_auth(monkeypatch):
    monkeypatch.delenv("HMIP_API_TOKEN", raising=False)
    with TestClient(app) as c:
        yield c


def test_no_auth_when_token_unset(client_no_auth):
    # dev mode: không bật auth
    assert client_no_auth.get("/api/latest").status_code == 200


def test_health_always_public(monkeypatch):
    monkeypatch.setattr("extensions.auth.API_TOKEN", "sectoken")
    monkeypatch.setattr("extensions.auth.is_enabled", lambda: True)
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200


def test_protected_route_requires_token(monkeypatch):
    # auth dùng API_TOKEN module-level → patch trực tiếp
    monkeypatch.setattr("extensions.auth.API_TOKEN", "sectoken")
    monkeypatch.setattr("extensions.auth.is_enabled", lambda: True)
    with TestClient(app) as c:
        assert c.get("/api/latest").status_code == 401
        assert c.get("/api/latest", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/api/latest", headers={"Authorization": "Bearer sectoken"}).status_code == 200


def test_dashboard_shell_public(monkeypatch):
    monkeypatch.setattr("extensions.auth.API_TOKEN", "sectoken")
    monkeypatch.setattr("extensions.auth.is_enabled", lambda: True)
    with TestClient(app) as c:
        # '/' được phép truy cập không token (UI tự login)
        assert c.get("/").status_code == 200


def test_is_enabled_reflects_env(monkeypatch):
    monkeypatch.setenv("HMIP_API_TOKEN", "x")
    import extensions.auth as auth

    importlib.reload(auth)
    try:
        assert auth.is_enabled() is True
    finally:
        importlib.reload(auth)
