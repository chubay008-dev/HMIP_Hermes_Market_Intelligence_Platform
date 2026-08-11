"""scheduler.py — quét giá định kỳ và đẩy cảnh báo.

Chạy độc lập:   python -m extensions.scheduler
Hoặc nhúng vào API (start.sh có thể gọi luôn).

Dùng APScheduler BlockingScheduler. Mỗi chu kỳ: quét toàn bộ catalog,
ghi SQLite (như đã làm), rồi với mỗi kết quả có quyết định khác
IGNORE → gửi Telegram (hoặc log fallback).

Cấu hình:
  HMIP_SCAN_INTERVAL_MIN   mặc định 30 (phút)
  HMIP_TELEGRAM_BOT_TOKEN / HMIP_TELEGRAM_CHAT_ID  (nếu có → push thật)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from extensions import db
from extensions.collect_adapters import _DEMO_CATALOG
from extensions.notifiers.telegram import is_configured, notify
from extensions.run_workflow import run_prc_001

log = logging.getLogger("hmip.scheduler")


def scan_once() -> dict[str, int]:
    """Quét 1 lượt; trả số liệu tóm tắt."""
    counts = {"scanned": 0, "alerts": 0, "escalations": 0, "errors": 0}
    for pid, meta in _DEMO_CATALOG.items():
        try:
            result = run_prc_001(pid, source="scheduler")
            counts["scanned"] += 1
            steps = result.get("steps", {})
            decision = (steps.get("decide") or {}).get("decision")
            if decision in ("ALERT", "ESCALATE", "HUMAN_REVIEW"):
                counts["alerts"] += 1
                if decision == "ESCALATE":
                    counts["escalations"] += 1
                notify(
                    decision=decision,
                    product_name=meta["product_name"],
                    price=(steps.get("compare") or {}).get("current_price"),
                    delta_percent=(steps.get("compare") or {}).get("delta_percent"),
                    base_price=result.get("base_price"),
                )
        except Exception as exc:  # noqa: BLE001
            counts["errors"] += 1
            log.exception("scan lỗi cho %s: %s", pid, exc)
    return counts


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    interval = int(os.getenv("HMIP_SCAN_INTERVAL_MIN", "30"))
    mode = "Telegram" if is_configured() else "console-fallback (chưa cấu hình bot)"
    log.info("HMIP scheduler khởi động — chu kỳ %s phút, notify=%s", interval, mode)
    log.info("Quét ngay lần đầu…")
    scan_once()
    sched = BlockingScheduler()
    sched.add_job(
        scan_once,
        trigger=IntervalTrigger(minutes=interval),
        id="hmip_scan",
        next_run_time=datetime.now() + timedelta(seconds=interval * 60),
        max_instances=1,
        coalesce=True,
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler dừng.")


if __name__ == "__main__":
    main()
