"""conftest — đảm bảo mọi test chạy ở dev-mode (không auth) trừ khi
test tự set token. Auth được bật bởi env HMIP_API_TOKENS / HMIP_API_TOKEN;
ở test ta muốn mặc định TẮT để test logic nghiệp vụ không bị 401.
"""

import pytest


@pytest.fixture(autouse=True)
def _no_auth_by_default(monkeypatch):
    monkeypatch.delenv("HMIP_API_TOKEN", raising=False)
    monkeypatch.delenv("HMIP_API_TOKENS", raising=False)
    import extensions.auth as auth

    auth.reload_tokens()  # ALLOWED_TOKENS rỗng → dev mode
    yield
    auth.reload_tokens()
