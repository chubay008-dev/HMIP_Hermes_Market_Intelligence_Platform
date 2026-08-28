"""external_watchdog.py — Dead man's switch pipeline, chạy NGOÀI GitHub (chỉ stdlib).

Bối cảnh (vụ 26-27/08/2026): GitHub Actions sập → run theo lịch bị miss và KHÔNG
tự chạy bù. Healthcheck trong repo (pipeline_healthcheck.py, PR #24) cũng là cron
GitHub nên chết theo → không ai phát hiện. Script này chạy trên OpenHands Cloud
Automation (cron 05:15-09:15, 11:15, 14:15 VN) — hạ tầng độc lập GitHub.

Mỗi lượt, theo thứ tự beer-price-scan → HMIP (reconcile cần dữ liệu scan sync sang):
  1. Có run event=schedule của workflow hôm nay (giờ VN)? → OK, skip.
  2. Đã có run workflow_dispatch hôm nay (user/agent chạy bù, hoặc lượt watchdog
     trước đã dispatch)? → skip, chống trùng.
  3. Chống false-positive do free-tier delay 2,5-3h (21-22/08): chỉ dispatch khi
     (a) có incident Actions trong ~30h qua (githubstatus), HOẶC (b) đã ≥08:00 VN
     (vượt cửa sổ delay tối đa quan sát được).
  4. Actions đang degraded → không dispatch (run cũng không nổ), tick sau thử lại.
  5. Riêng HMIP: chỉ dispatch sau khi beer-scan có run HOÀN TẤT hôm nay — tránh
     race: reconcile push commit → Render deploy → app-sync collect giữa chừng bị
     sync của beer-scan push commit mới → swap instance → 502 (vụ 28/08).

Không gửi Telegram/Discord trực tiếp (không có secret bot trên OpenHands) — khi
dispatch chạy bù thành công, chính pipeline gửi tin "HOÀN TẤT pipeline" như thường.

Env:
  GITHUB_TOKEN (qua get_secret) — token có quyền actions:write trên cả 2 repo
  DRY_RUN=1                     — chỉ in quyết định, không dispatch
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))
GH_API = "https://api.github.com"
GH_STATUS_SUMMARY = "https://www.githubstatus.com/api/v2/summary.json"
GH_STATUS_INCIDENTS = "https://www.githubstatus.com/api/v2/incidents.json"

# Thứ tự quan trọng: scan trước, HMIP sau (reconcile đọc dữ liệu scan sync sang).
BEER_REPO = "chubay008-dev/beer-price-scan"
BEER_WORKFLOW = "daily-scan.yml"
HMIP_REPO = "chubay008-dev/HMIP_Hermes_Market_Intelligence_Platform"
HMIP_WORKFLOW = "reconcile.yml"

DELAY_BUFFER_HOUR_VN = 8  # sau 08:00 VN mới dispatch khi không có bằng chứng incident
INCIDENT_LOOKBACK_H = 30

_UA = {"User-Agent": "hmip-external-watchdog (https://github.com/chubay008-dev, 1.0)"}


def get_secret(name: str) -> str:
    """Lấy secret từ agent server. Deployment 28/08/2026 KHÔNG inject
    AGENT_SERVER_URL — chỉ có RUNTIME_URL (public URL của sandbox) + SESSION_API_KEY.
    Thử lần lượt cả hai."""
    key = os.environ.get("SESSION_API_KEY") or os.environ.get("OH_SESSION_API_KEYS_0", "")
    for base in (os.environ.get("AGENT_SERVER_URL", ""), os.environ.get("RUNTIME_URL", "")):
        base = base.rstrip("/")
        if not base:
            continue
        req = urllib.request.Request(f"{base}/api/settings/secrets/{name}",
                                     headers={"X-Session-API-Key": key})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode().strip()
        except Exception as e:
            print(f"WARN get_secret qua {base[:30]}...: {e}")
    raise RuntimeError(f"không lấy được secret {name} từ agent server")


def fire_callback(status: str = "COMPLETED", error: str | None = None) -> None:
    """Best effort — deployment hiện tại không inject AUTOMATION_CALLBACK_*;
    run status theo exit code của script (0 = COMPLETED)."""
    url = os.environ.get("AUTOMATION_CALLBACK_URL", "")
    if not url:
        return
    body = {"status": status, "run_id": os.environ.get("AUTOMATION_RUN_ID", "")}
    if error:
        body["error"] = error
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.environ.get('AUTOMATION_CALLBACK_API_KEY', '')}",
    })
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception as e:
        print(f"Callback error (non-fatal): {e}")


def _req(url: str, headers: dict, data: dict | None = None) -> tuple[int, dict]:
    h = {"Content-Type": "application/json", **_UA, **headers}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else {})


def _gh(path: str, token: str, data: dict | None = None) -> tuple[int, dict]:
    return _req(f"{GH_API}{path}", {"Authorization": f"Bearer {token}"}, data)


def fetch_runs_today(repo: str, workflow_file: str, token: str) -> dict[str, list[dict]]:
    """Run của workflow trong ngày VN hôm nay, tách theo event (schedule/dispatch)."""
    today_vn = datetime.now(VN_TZ).date()
    _, data = _gh(f"/repos/{repo}/actions/runs?per_page=50&branch=main", token)
    out: dict[str, list[dict]] = {"schedule": [], "workflow_dispatch": []}
    for run in data.get("workflow_runs", []):
        if not run.get("path", "").endswith(workflow_file):
            continue
        created_vn = datetime.fromisoformat(
            run["created_at"].replace("Z", "+00:00")).astimezone(VN_TZ).date()
        if created_vn == today_vn and run.get("event") in out:
            out[run["event"]].append(run)
    return out


def actions_degraded_now() -> bool:
    try:
        _, summary = _req(GH_STATUS_SUMMARY, {})
        for comp in summary.get("components", []):
            if "Actions" in comp.get("name", ""):
                status = comp.get("status", "unknown")
                print(f"GitHub Actions component: {status}")
                return status not in ("operational", "unknown")
    except Exception as e:
        print(f"WARN không đọc được githubstatus summary: {e}")
    return False


def actions_incident_recently() -> bool:
    """Có incident nào đụng Actions trong INCIDENT_LOOKBACK_H giờ qua không
    (kể cả đã resolved — run đã miss trong lúc sự cố thì vẫn cần chạy bù)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=INCIDENT_LOOKBACK_H)
    try:
        _, data = _req(GH_STATUS_INCIDENTS, {})
        for inc in data.get("incidents", []):
            haystack = inc.get("name", "") + " " + " ".join(
                c.get("name", "") for c in inc.get("components", []))
            if "Actions" not in haystack:
                continue
            created = datetime.fromisoformat(inc["created_at"].replace("Z", "+00:00"))
            if created >= cutoff:
                print(f"Incident Actions gần đây: {inc['name']} ({inc['status']}, "
                      f"{inc['created_at'][:16]})")
                return True
    except Exception as e:
        print(f"WARN không đọc được githubstatus incidents: {e}")
    return False


def dispatch(repo: str, workflow_file: str, token: str) -> int:
    st, _ = _gh(f"/repos/{repo}/actions/workflows/{workflow_file}/dispatches",
                token, {"ref": "main"})
    return st


def allowed_to_dispatch(now_vn: datetime) -> bool:
    """Chống false-positive khi free-tier chỉ đang DELAY (không phải drop)."""
    if now_vn.hour >= DELAY_BUFFER_HOUR_VN:
        return True
    return actions_incident_recently()


def check_repo(repo: str, workflow_file: str, token: str, now_vn: datetime,
               label: str, runs: dict[str, list[dict]]) -> str:
    """Trả về: ok | caught_up | wait | degraded | dispatched | error."""
    print(f"[{label}] hôm nay: {len(runs['schedule'])} schedule, "
          f"{len(runs['workflow_dispatch'])} dispatch")
    if runs["schedule"]:
        return "ok"
    if runs["workflow_dispatch"]:
        return "caught_up"
    if not allowed_to_dispatch(now_vn):
        print(f"[{label}] chưa thấy run nhưng chưa đủ bằng chứng drop "
              f"(trước {DELAY_BUFFER_HOUR_VN}h VN, không incident) — chờ tick sau.")
        return "wait"
    if actions_degraded_now():
        print(f"[{label}] Actions đang degraded — dispatch cũng không nổ, tick sau thử lại.")
        return "degraded"
    if os.environ.get("DRY_RUN") == "1":
        print(f"[{label}] DRY RUN — đáng lẽ dispatch {workflow_file}")
        return "dispatched"
    st = dispatch(repo, workflow_file, token)
    print(f"[{label}] dispatch {workflow_file}: HTTP {st} "
          f"→ https://github.com/{repo}/actions")
    return "dispatched" if st in (201, 204) else "error"


def main() -> None:
    now_vn = datetime.now(VN_TZ)
    print(f"=== External watchdog {now_vn.strftime('%d/%m/%Y %H:%M')} (giờ VN) ===")
    token = os.environ.get("GITHUB_TOKEN") or get_secret("GITHUB_TOKEN")

    beer_runs = fetch_runs_today(BEER_REPO, BEER_WORKFLOW, token)
    beer = check_repo(BEER_REPO, BEER_WORKFLOW, token, now_vn, "beer-scan", beer_runs)

    # HMIP chỉ chạy bù sau khi beer-scan HOÀN TẤT (scan ~20-25' → thường tick sau).
    beer_done = any(r.get("status") == "completed"
                    for r in beer_runs["schedule"] + beer_runs["workflow_dispatch"])
    if beer == "ok" or beer_done:
        hmip_runs = fetch_runs_today(HMIP_REPO, HMIP_WORKFLOW, token)
        hmip = check_repo(HMIP_REPO, HMIP_WORKFLOW, token, now_vn, "HMIP", hmip_runs)
    else:
        print("[HMIP] beer-scan chưa xong — chờ tick sau (tránh race deploy Render).")
        hmip = "wait"

    print(f"=== Kết quả: beer-scan={beer}, HMIP={hmip} ===")
    if "error" in (beer, hmip):
        raise RuntimeError("dispatch thất bại — xem log trên.")


if __name__ == "__main__":
    try:
        main()
        fire_callback("COMPLETED")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        fire_callback("FAILED", f"{type(e).__name__}: {e}")
        sys.exit(1)
