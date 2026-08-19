"""clerk_auth.py — xác thực session Clerk (tùy chọn, song song với token tĩnh).

Thiết kế:
- CHỈ bật khi có env CLERK_SECRET_KEY. Nếu không → is_enabled()=False,
  mọi hàm trả về "không xác thực được" một cách an toàn (không crash).
- Không import clerk-backend-api ở top-level (tránh lỗi import nếu chưa pip
  install). Import bên trong hàm -> graceful degradation trên Render free
  nếu package chưa cài.
- verify_clerk_token(token) trả về (ok: bool, user_id: str|None).
  Token là Clerk session token (JWT __session_) gửi qua header
  Authorization: Bearer <session_token>.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("hmip.clerk")

_SECRET = (os.getenv("CLERK_SECRET_KEY") or "").strip()


def is_enabled() -> bool:
    """Clerk auth chỉ bật khi admin cấu hình CLERK_SECRET_KEY."""
    return bool(_SECRET)


def _client():
    """Trả về Clerk client hoặc None nếu chưa cài SDK / thiếu key."""
    if not _SECRET:
        return None
    try:
        from clerk_backend_api import Clerk  # type: ignore
    except Exception as exc:  # noqa: BLE001
        log.warning("clerk-backend-api chưa cài, bỏ qua Clerk auth: %s", exc)
        return None
    try:
        # clerk-backend-api >= 6 dùng bearer_auth= thay vì api_key=
        try:
            return Clerk(bearer_auth=_SECRET)
        except TypeError:
            return Clerk(api_key=_SECRET)  # fallback bản cũ
    except Exception as exc:  # noqa: BLE001
        log.warning("Khởi tạo Clerk client lỗi: %s", exc)
        return None


def verify_clerk_token(token: str | None) -> tuple[bool, str | None]:
    """Xác thực Clerk session token.

    Trả về (ok, user_id). Nếu Clerk không bật / SDK thiếu / token sai ->
    (False, None). Không bao giờ raise.
    """
    if not token:
        return False, None
    client = _client()
    if client is None:
        return False, None
    try:
        # verify trả về session object; session.user_id là định danh user.
        session = client.sessions.verify(token)
        if session and getattr(session, "is_valid", True):
            uid = getattr(session, "user_id", None)
            return True, (uid or "clerk-user")
    except Exception as exc:  # noqa: BLE001
        log.debug("Clerk verify fail: %s", exc)
    return False, None
