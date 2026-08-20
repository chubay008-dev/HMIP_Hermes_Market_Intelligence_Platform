"""auth.py — bảo vệ API khi mở ra internet.

Thiết kế multi-token (Phương án A):
- Đọc danh sách token được phép từ env HMIP_API_TOKENS (JSON array).
  Ví dụ: HMIP_API_TOKENS='["hmip-chubay-9k2x","hmip-user2-3f8a"]'
- Backward-compat: nếu chỉ có HMIP_API_TOKEN (chuỗi đơn, cũ) → coi là 1 token.
- Token nào nằm trong danh sách đều hợp lệ → mỗi người dùng 1 token riêng,
  thu hồi (revoke) bằng cách bỏ token đó khỏi list rồi redeploy.
- KHÔNG dùng SQLite (Render free ephemeral FS mất data) — token định nghĩa
  qua env, deploy nào cũng tái tạo giống hệt.

Không đổi kernel; chỉ là lớp ngoài cùng. Route /api/health, /docs, /openapi.json,
/redoc, /static được miễn trừ.
"""

from __future__ import annotations

import json
import logging
import os

from fastapi import FastAPI, HTTPException, Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED

log = logging.getLogger("hmip.auth")

# Danh sách token hợp lệ (set để lookup O(1))
ALLOWED_TOKENS: set[str] = set()


def _load_tokens() -> set[str]:
    """Đọc token từ env.

    Ưu tiên HMIP_API_TOKENS (JSON array). Nếu không có, fallback HMIP_API_TOKEN
    (chuỗi đơn, tương thích ngược). Trả về set rỗng nếu không có gì.
    """
    raw = os.getenv("HMIP_API_TOKENS", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return {str(t).strip() for t in data if str(t).strip()}
            # Nếu là chuỗi đơn trong JSON (hiếm) → coi như 1 token
            return {str(data).strip()} if str(data).strip() else set()
        except (json.JSONDecodeError, TypeError):
            log.warning(
                "HMIP_API_TOKENS không phải JSON hợp lệ, bỏ qua. Giá trị: %.50s",
                raw,
            )
    single = os.getenv("HMIP_API_TOKEN", "").strip()
    if single:
        return {single}
    return set()


# Load lúc import; reload() sẽ gọi lại khi test thay đổi env.
ALLOWED_TOKENS = _load_tokens()


def reload_tokens() -> None:
    """Đọc lại token từ env (dùng khi test monkeypatch env)."""
    global ALLOWED_TOKENS
    ALLOWED_TOKENS = _load_tokens()


def is_enabled() -> bool:
    return bool(ALLOWED_TOKENS)


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _check(token: str | None) -> bool:
    """Chấp nhận token tĩnh HOẶC Clerk session token (song song).

    - Token tĩnh (HMIP_API_TOKENS / HMIP_API_TOKEN) → cron + dev mode.
    - Clerk session token (JWT __session_) → người mở web login qua Clerk.
    """
    if token and token in ALLOWED_TOKENS:
        return True
    # Clerk chỉ chạy nếu admin cấu hình CLERK_SECRET_KEY.
    try:
        from extensions.clerk_auth import is_enabled as clerk_on, verify_clerk_token
        if clerk_on():
            ok, _uid = verify_clerk_token(token)
            return ok
    except Exception:  # noqa: BLE001  - Clerk chưa cài/import lỗi -> bỏ qua
        pass
    return False


async def require_token(request: Request) -> None:
    """Dependency: từ chối nếu thiếu/sai token."""
    if not is_enabled():
        return  # dev mode: không bật auth
    token = _extract_token(request)
    if not _check(token):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Thiếu hoặc sai token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Các path không cần token. Dashboard '/' chỉ exempt chính xác nó
# (không dùng startswith('/') vì sẽ miễn trừ mọi route).
# /api/auth/clerk-config PHẢI public — frontend gọi khi chưa login để
# lấy publishable key + biết Clerk có bật không.
_EXEMPT_EXACT = ("/api/health", "/api/auth/clerk-config", "/docs", "/openapi.json", "/redoc", "/static", "/", "/pi", "/workspace", "/favicon.ico")
_EXEMPT_PREFIX = ("/api/health", "/docs", "/openapi.json", "/redoc", "/static")


def protect_app(app: FastAPI) -> None:
    """Gắn middleware kiểm tra token cho mọi route trừ _EXEMPT_PREFIXES.

    Dùng middleware thay vì Depends trên từng route → áp dụng toàn cục,
    không quên route nào. Route gốc '/' (dashboard) BỊ bảo vệ — đúng,
    vì mở internet không thể để ai cũng xem được giá nội bộ.
    """

    @app.middleware("http")
    async def _auth_middleware(request: Request, call_next):
        if not is_enabled():
            return await call_next(request)
        path = request.url.path
        if path in _EXEMPT_EXACT or any(path.startswith(p) for p in _EXEMPT_PREFIX):
            return await call_next(request)
        token = _extract_token(request)
        if not _check(token):
            return JSONResponse(
                status_code=HTTP_401_UNAUTHORIZED,
                content={"detail": "Thiếu hoặc sai token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)
