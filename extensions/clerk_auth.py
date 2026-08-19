"""clerk_auth.py - xác thực session Clerk (tùy chọn, song song với token tĩnh).

Thiết kế:
- CHỈ bật khi có env CLERK_SECRET_KEY. Nếu không -> is_enabled()=False.
- Token là Clerk session JWT (RS256, ký bởi Clerk). Verify qua JWKS public key
  của instance (chuẩn Clerk: https://clerk.com/docs/backend/verify).
- verify_clerk_token(token) trả (ok, user_id). Không bao giờ raise.
"""

from __future__ import annotations

import logging
import os
import time

log = logging.getLogger("hmip.clerk")

_SECRET = (os.getenv("CLERK_SECRET_KEY") or "").strip()
# Frontend API domain lấy từ publishable key (pk_test_<base64 domain>)
_PUB = (os.getenv("CLERK_PUBLISHABLE_KEY") or "").strip()


def is_enabled() -> bool:
    return bool(_SECRET)


def _jwks_url() -> str:
    """Lấy JWKS URL từ publishable key hoặc mặc định api.clerk.com."""
    global _PUB
    if not _PUB:
        # fallback: dùng domain mặc định của Clerk
        return "https://api.clerk.com/v1/jwks"
    try:
        import base64, json
        # pk_test_xxx  -> xxx là base64url của "instance_domain.clerk.accounts.dev"
        raw = _PUB.split("_", 1)[-1]
        raw += "=" * (-len(raw) % 4)
        domain = json.loads(base64.urlsafe_b64decode(raw).decode()).strip()
        return f"https://{domain}/.well-known/jwks.json"
    except Exception:
        return "https://api.clerk.com/v1/jwks"


def _get_jwks():
    import requests
    url = _jwks_url()
    # api.clerk.com cần Bearer, domain.clerk.accounts.dev thì public
    headers = {}
    if "api.clerk.com" in url and _SECRET:
        headers["Authorization"] = f"Bearer {_SECRET}"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def verify_clerk_token(token: str | None) -> tuple[bool, str | None]:
    """Xác thực Clerk session JWT qua JWKS (RS256). Trả (ok, user_id)."""
    if not token or not _SECRET:
        return False, None
    try:
        import jwt
        from jwt.algorithms import RSAAlgorithm

        jwks = _get_jwks()
        kid = jwt.get_unverified_header(token).get("kid")
        key = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key = RSAAlgorithm.from_jwk(__import__("json").dumps(k))
                break
        if key is None:
            return False, None
        # Clerk session token: verify chữ ký RS256; bỏ qua aud (satellite domain)
        payload = jwt.decode(
            token, key,
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_exp": True},
        )
        uid = payload.get("sub") or payload.get("user_id")
        return True, (uid or "clerk-user")
    except Exception as exc:  # noqa: BLE001
        log.debug("Clerk verify fail: %s", exc)
    return False, None
