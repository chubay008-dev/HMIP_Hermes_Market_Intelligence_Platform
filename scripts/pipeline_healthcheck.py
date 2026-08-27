"""pipeline_healthcheck.py — Dead man's switch cho pipeline hằng ngày (chỉ stdlib).

Vấn đề (vụ sự cố 26-27/08/2026): GitHub Actions gặp sự cố → các run theo LỊCH
(schedule) bị bỏ qua hoàn toàn và KHÔNG tự chạy bù sau khi dịch vụ hồi phục →
không có email báo cáo sáng mà không ai hay biết.

Job này chạy SAU giờ pipeline (cron riêng, vd 04:45 / 07:45 / 10:45 VN) và:
  1. Kiểm tra "dead man's switch": workflow chính (EXPECTED_WORKFLOW_FILE) có run
     event=schedule nào trong NGÀY HÔM NAY (giờ VN) chưa? Có → im lặng, exit 0.
  2. Thiếu run → hỏi GitHub Status API (githubstatus.com, public, không cần auth):
       - Actions đang sự cố → CẢNH BÁO Telegram/Discord + mở session OpenHands
         (ghi nhận sự cố, theo dõi & chạy bù khi dịch vụ hồi phục).
       - Actions đã operational → TỰ CHẠY BÙ (workflow_dispatch) + thông báo.
  3. Chống chạy bù trùng: nếu hôm nay đã có run workflow_dispatch (user chạy tay
     hoặc lượt healthcheck trước đã dispatch) → không dispatch lại, chỉ log.

Lưu ý giới hạn: healthcheck cũng chạy trên GitHub Actions — khi Actions sập HOÀN
TOÀN thì chính nó cũng không chạy được. Nó bắt được 2 tình huống chính: (a) Actions
hồi phục trong ngày (cron lặp nhiều lần/ngày → lượt đầu tiên sau khi hồi sẽ phát
hiện run bị miss và chạy bù), (b) Actions degraded một phần (run bị miss nhưng
healthcheck vẫn chạy — đúng như vụ 27/08).

Env:
  GH_TOKEN (bắt buộc)          — github.token của workflow (cần actions: write để dispatch)
  GITHUB_REPOSITORY            — owner/repo (workflow tự set)
  EXPECTED_WORKFLOW_FILE       — tên file workflow chính (vd "reconcile.yml")
  REPO_LABEL                   — nhãn hiển thị trong tin nhắn
  OPENHANDS_API_KEY (tuỳ chọn) — có thì mở session OpenHands Cloud khi có sự cố
  TELEGRAM_DONE_BOT_TOKEN / TELEGRAM_DONE_CHAT_ID     — kênh cảnh báo (tuỳ chọn)
  DISCORD_DONE_BOT_TOKEN / DISCORD_DONE_CHANNEL_ID    — kênh cảnh báo (tuỳ chọn)
  DRY_RUN=1                    — chỉ in quyết định, không dispatch/notify/session

Script KHÔNG BAO GIỜ làm fail workflow (mọi lỗi chỉ WARN, exit 0).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))
GH_API = "https://api.github.com"
OH_BASE = "https://app.all-hands.dev"
GH_STATUS_SUMMARY = "https://www.githubstatus.com/api/v2/summary.json"
GH_STATUS_INCIDENTS = "https://www.githubstatus.com/api/v2/incidents/unresolved.json"

_UA = {"User-Agent": "hmip-healthcheck (https://github.com/chubay008-dev, 1.0)"}


def _req(url: str, headers: dict, data: dict | None = None,
         method: str | None = None) -> tuple[int, dict]:
    h = {"Content-Type": "application/json", **_UA, **headers}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else {})


def _gh_get(path: str) -> dict:
    return _req(f"{GH_API}{path}", {"Authorization": f"Bearer {os.environ['GH_TOKEN']}"})[1]


def _gh_post(path: str, data: dict) -> int:
    return _req(f"{GH_API}{path}", {"Authorization": f"Bearer {os.environ['GH_TOKEN']}"},
                data=data)[0]


# ---------------------------------------------------------------------------
# 1. Dead man's switch — run theo lịch hôm nay (giờ VN) đã tồn tại chưa?
# ---------------------------------------------------------------------------

def fetch_today_runs(repo: str, workflow_file: str) -> tuple[list[dict], list[dict]]:
    """Trả về (scheduled_runs, dispatch_runs) của workflow_file trong ngày VN hôm nay.

    Lọc phía client theo created_at quy về giờ VN (run 03:00 VN = 20:00 UTC hôm
    trước → không dùng được tham số ?created= của API vì nó theo ngày UTC).
    """
    today_vn = datetime.now(VN_TZ).date()
    data = _gh_get(f"/repos/{repo}/actions/runs?per_page=50&branch=main")
    scheduled, dispatched = [], []
    for run in data.get("workflow_runs", []):
        if not run.get("path", "").endswith(workflow_file):
            continue
        created_vn = datetime.fromisoformat(
            run["created_at"].replace("Z", "+00:00")).astimezone(VN_TZ).date()
        if created_vn != today_vn:
            continue
        event = run.get("event")
        if event == "schedule":
            scheduled.append(run)
        elif event == "workflow_dispatch":
            dispatched.append(run)
    return scheduled, dispatched


# ---------------------------------------------------------------------------
# 2. GitHub Status API — Actions có đang sự cố không?
# ---------------------------------------------------------------------------

def check_github_status() -> tuple[str, list[str]]:
    """Trả về (trạng thái component Actions, tên các incident chưa resolve đụng Actions)."""
    comp_status = "unknown"
    try:
        summary = _req(GH_STATUS_SUMMARY, {})[1]
        for comp in summary.get("components", []):
            if "Actions" in comp.get("name", ""):
                comp_status = comp.get("status", "unknown")
                break
    except Exception as e:
        print(f"WARN không đọc được githubstatus summary: {e}", file=sys.stderr)
    incidents: list[str] = []
    try:
        data = _req(GH_STATUS_INCIDENTS, {})[1]
        for inc in data.get("incidents", []):
            names = " ".join(c.get("name", "") for c in inc.get("components", []))
            if "Actions" in names or "Actions" in inc.get("name", ""):
                incidents.append(f"{inc.get('name')} ({inc.get('status')})")
    except Exception as e:
        print(f"WARN không đọc được githubstatus incidents: {e}", file=sys.stderr)
    return comp_status, incidents


# ---------------------------------------------------------------------------
# 3. Chạy bù + thông báo + session OpenHands
# ---------------------------------------------------------------------------

def dispatch_workflow(repo: str, workflow_file: str, ref: str = "main") -> int:
    return _gh_post(f"/repos/{repo}/actions/workflows/{workflow_file}/dispatches",
                    {"ref": ref})


def notify(msg: str) -> None:
    """Gửi cảnh báo qua bot hoàn-tất (Telegram + Discord). Best effort, không raise."""
    results = []
    token, chat = (os.environ.get("TELEGRAM_DONE_BOT_TOKEN", ""),
                   os.environ.get("TELEGRAM_DONE_CHAT_ID", ""))
    if token and chat:
        try:
            st, _ = _req(f"https://api.telegram.org/bot{token}/sendMessage",
                         {}, {"chat_id": chat, "text": msg})
            results.append(f"Telegram {st}")
        except Exception as e:
            results.append(f"Telegram lỗi: {e}")
    dc_token, dc_ch = (os.environ.get("DISCORD_DONE_BOT_TOKEN", ""),
                       os.environ.get("DISCORD_DONE_CHANNEL_ID", ""))
    if dc_token and dc_ch:
        try:
            st, _ = _req(f"https://discord.com/api/v10/channels/{dc_ch}/messages",
                         {"Authorization": f"Bot {dc_token}"},
                         {"content": msg, "allowed_mentions": {"parse": []}})
            results.append(f"Discord {st}")
        except Exception as e:
            results.append(f"Discord lỗi: {e}")
    print("healthcheck notify:", "; ".join(results) or "SKIP(thiếu env)")


def build_openhands_prompt(repo: str, workflow_file: str, repo_label: str,
                           comp_status: str, incidents: list[str]) -> str:
    now_vn = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M")
    inc_txt = "\n".join(f"- {i}" for i in incidents) or "(không có incident đang mở)"
    return f"""Bạn là agent theo dõi sự cố pipeline hằng ngày của repo {repo}.

Lúc {now_vn} (giờ VN), healthcheck phát hiện workflow "{workflow_file}" KHÔNG có run
theo lịch nào trong ngày hôm nay — pipeline báo cáo buổi sáng ({repo_label}) bị miss.
Trạng thái GitHub Actions lúc kiểm tra: {comp_status}
Incident đang mở:
{inc_txt}

Nhiệm vụ:
1. Kiểm tra https://www.githubstatus.com/api/v2/summary.json (component "GitHub Actions").
2. Nếu Actions ĐÃ operational: chạy bù pipeline bằng cách dispatch workflow chính,
   ví dụ: `gh workflow run {workflow_file} --repo {repo}` (repo beer-price-scan có
   workflow daily-scan.yml tương ứng — nếu token không đủ quyền cross-repo thì ghi
   rõ trong báo cáo để chủ repo chạy tay, KHÔNG tự ý tạo PAT mới).
3. Sau khi dispatch, theo dõi run (`gh run watch` / `gh run list --repo {repo}`)
   đến khi xong; xác nhận các bước gửi email/thông báo thành công.
4. TUYỆT ĐỐI KHÔNG: đổi secrets, tắt workflow, push thẳng lên main.
5. Kết thúc bằng báo cáo ngắn (tiếng Việt): tình trạng sự cố, run chạy bù (link),
   email báo cáo ngày hôm nay đã được gửi hay chưa."""


def start_openhands_session(prompt: str, title: str) -> str | None:
    api_key = os.environ.get("OPENHANDS_API_KEY", "")
    if not api_key:
        print("SKIP OpenHands session: thiếu OPENHANDS_API_KEY")
        return None
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    try:
        st, body = _req(f"{OH_BASE}/api/v1/app-conversations",
                        {"Authorization": f"Bearer {api_key}"},
                        {"initial_message": {"content": [{"type": "text", "text": prompt}]},
                         "selected_repository": repo, "selected_branch": "main",
                         "title": title})
        print(f"OpenHands start: HTTP {st}")
        conv_id = body.get("app_conversation_id")
        return f"{OH_BASE}/conversations/{conv_id}" if conv_id else None
    except Exception as e:
        print(f"WARN không mở được session OpenHands: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------

def main() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    workflow_file = os.environ.get("EXPECTED_WORKFLOW_FILE", "reconcile.yml")
    repo_label = os.environ.get("REPO_LABEL", workflow_file)
    now_vn = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M")

    scheduled, dispatched = fetch_today_runs(repo, workflow_file)
    print(f"runs hôm nay ({workflow_file}): {len(scheduled)} schedule, "
          f"{len(dispatched)} workflow_dispatch")

    if scheduled:
        ok = [r for r in scheduled if r.get("conclusion") in (None, "success")]
        print(f"OK: đã có {len(scheduled)} run theo lịch "
              f"({len(ok)} đang chạy/thành công) — không cần hành động.")
        if not ok:
            print("Lưu ý: run theo lịch hôm nay có kết luận khác success — "
                  "job fail đã có auto_remediate riêng xử lý, healthcheck không can thiệp.")
        return

    # --- Thiếu run theo lịch hôm nay → điều tra ---------------------------------
    comp_status, incidents = check_github_status()
    print(f"GitHub Actions status: {comp_status}; incidents: {incidents or '[]'}")
    already_caught_up = bool(dispatched)
    degraded = comp_status not in ("operational", "unknown") or bool(incidents)

    if os.environ.get("DRY_RUN") == "1":
        print(f"DRY RUN — degraded={degraded}, already_caught_up={already_caught_up}")
        return

    if already_caught_up:
        print("Hôm nay đã có run workflow_dispatch (đã chạy bù) — chỉ log, không làm gì.")
        return

    if degraded:
        msg = (f"🚨 CẢNH BÁO PIPELINE {now_vn} (giờ VN)\n"
               f"Không thấy run theo lịch của «{repo_label}» hôm nay.\n"
               f"GitHub Actions đang sự cố: {comp_status}"
               + (f"\nIncident: {'; '.join(incidents)}" if incidents else "")
               + "\nĐã mở session OpenHands theo dõi — sẽ chạy bù khi dịch vụ hồi phục.")
        prompt = build_openhands_prompt(repo, workflow_file, repo_label,
                                        comp_status, incidents)
        session = start_openhands_session(
            prompt, f"Healthcheck: miss pipeline {repo.split('/')[-1]} {now_vn}")
        if session:
            msg += f"\nSession: {session}"
        notify(msg)
        return

    # Actions trông bình thường nhưng run bị miss → chạy bù ngay.
    status = dispatch_workflow(repo, workflow_file)
    print(f"dispatch {workflow_file}: HTTP {status}")
    if status in (204, 201):
        notify(f"🔁 CHẠY BÙ PIPELINE {now_vn} (giờ VN)\n"
               f"Không thấy run theo lịch của «{repo_label}» hôm nay, GitHub Actions "
               f"đã operational → đã trigger workflow_dispatch chạy bù.\n"
               f"https://github.com/{repo}/actions")
    else:
        notify(f"⚠️ PIPELINE {now_vn} (giờ VN): «{repo_label}» miss run theo lịch, "
               f"dispatch chạy bù trả HTTP {status} — cần kiểm tra thủ công.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"WARN pipeline_healthcheck lỗi: {type(e).__name__}: {e}", file=sys.stderr)
