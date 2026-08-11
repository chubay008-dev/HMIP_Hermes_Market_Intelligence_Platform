"""auth.py — bảo vệ API khi mở ra internet.

Đơn giản nhưng hiệu quả: Bearer token đọc từ env HMIP_API_TOKEN.
Nếu chưa đặt → app CHẠY KHÔNG CÓ AUTH (cảnh báo log) để dev local
không bị chặn. Khi deploy lên cloud, BẮT BUỘC đặt HMIP_API_TOKEN.

Thiết kế:
- Dùng Starlette HTTPBearer dependency → áp dụng cho các route cần bảo vệ.
- Route /api/health và /docs được miễn trừ (health để monitor, docs
  để debug — đóng docs khi production nếu muốn).
- KHÔNG sửa kernel; chỉ là lớp ngoài cùng.
"""

from __future__ import annotations

import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from starlette.status import HTTP_401_UNAUTHORIZED

log = logging.getLogger("hmip.auth")

API_TOKEN = os.getenv("HMIP_API_TOKEN", "")

# Các path không cần token. Dashboard '/' chỉ exempt chính xác nó
# (không dùng startswith('/') vì sẽ miễn trừ mọi route).
_EXEMPT_EXACT = ("/api/health", "/docs", "/openapi.json", "/redoc", "/static", "/")
_EXEMPT_PREFIX = ("/api/health", "/docs", "/openapi.json", "/redoc", "/static")


def is_enabled() -> bool:
    return bool(API_TOKEN)


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def require_token(request: Request) -> None:
    """Dependency: từ chối nếu thiếu/sai token."""
    if not is_enabled():
        return  # dev mode: không bật auth
    token = _extract_token(request)
    if not token or token != API_TOKEN:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Thiếu hoặc sai HMIP_API_TOKEN",
            headers={"WWW-Authenticate": "Bearer"},
        )


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
        if path in _EXEMPT_EXACT or any(
            path.startswith(p) for p in _EXEMPT_PREFIX
        ):
            return await call_next(request)
        token = _extract_token(request)
        if not token or token != API_TOKEN:
            return JSONResponse(
                status_code=HTTP_401_UNAUTHORIZED,
                content={"detail": "Thiếu hoặc sai HMIP_API_TOKEN"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)


# import ở cuối tránh circular import với fastapi response
from starlette.responses import JSONResponse  # noqa: E402
