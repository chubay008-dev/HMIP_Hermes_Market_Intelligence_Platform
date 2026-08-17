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


@pytest.fixture(autouse=True)
def _stop_scheduler_after_test():
    """Dừng BackgroundScheduler sau mỗi test để tránh thread leak.

    test_autoscan_lifecycle / test_api_endpoints start scheduler (lifespan
    hoặc POST /api/autoscan/start). scan_once quét nhiều SP; nếu thread
    còn sống khi test sau monkeypatch DEFAULT_DB_PATH sang temp_db khác,
    scan_once chèn SP lạ vào temp_db đó → test_db_upsert_is_idempotent fail
    (race: 2 rows thay vì 1). Shutdown + remove jobs + recreate để test
    sau start lại được (APScheduler không restart sau shutdown).
    """
    yield
    try:
        from extensions import api as _api
        sched = getattr(_api, "_auto_scheduler", None)
        if sched is not None:
            try:
                sched.remove_all_jobs()
            except Exception:
                pass
            if sched.running:
                try:
                    sched.shutdown(wait=False)
                except Exception:
                    pass
            from apscheduler.schedulers.background import BackgroundScheduler
            _api._auto_scheduler = BackgroundScheduler()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_notify_rate_limit():
    """Reset state anti-spam notify (cả 2 hệ) giữa các test."""
    yield
    try:
        from extensions.notifiers import rate_limit as _rl2
        _rl2.reset()
    except Exception:
        pass
    try:
        from extensions.pi import notifier as _pi_notifier
        if hasattr(_pi_notifier, "reset_notify_state"):
            _pi_notifier.reset_notify_state()
    except Exception:
        pass
