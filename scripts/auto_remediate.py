# -*- coding: utf-8 -*-
"""auto_remediate.py — Job fail → tự mở OpenHands Cloud session chẩn đoán + sửa + mở PR.

Chạy trong workflow với `if: failure()` (trước step thông báo hoàn tất):
  1. Thu thập step fail + log lỗi của run hiện tại (qua `gh run view`).
  2. Gọi OpenHands Cloud API `POST /api/v1/app-conversations` mở session agent
     với prompt tự-contained (repo, run URL, step fail, log lỗi, chỉ dẫn xử lý).
     Agent được phép: chẩn đoán, sửa tối thiểu, mở PR — KHÔNG merge, KHÔNG đổi secrets.
  3. Báo kết quả khởi động (link run + link session) về Telegram + Discord.

Env bắt buộc: OPENHANDS_API_KEY, GH_TOKEN (github.token), GITHUB_REPOSITORY,
GITHUB_RUN_ID, GITHUB_WORKFLOW, JOB_LABEL. Thiếu OPENHANDS_API_KEY -> SKIP.
DRY_RUN=1 -> chỉ in payload, không gọi API (dùng để test).
Script KHÔNG BAO GIỜ làm fail workflow (mọi lỗi chỉ WARN).
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

OH_BASE = "https://app.all-hands.dev"
LOG_TAIL = 6000


def _post(url: str, data: dict, headers: dict | None = None) -> tuple[int, dict]:
    h = {"Content-Type": "application/json",
         "User-Agent": "DiscordBot (https://github.com/chubay008-dev, 1.0)"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return r.status, (json.loads(body) if body else {})


def _gh(args: list[str]) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True,
                          timeout=120).stdout


def collect_failure_info(repo: str, run_id: str) -> tuple[str, str]:
    """Trả về (danh sách step fail, log lỗi phần cuối)."""
    failed_steps = "(không xác định)"
    try:
        jobs = json.loads(_gh(["run", "view", run_id, "--repo", repo, "--json", "jobs"]))
        names = [f"{j['name']} › {s['name']}" for j in jobs.get("jobs", [])
                 for s in j.get("steps", []) if s.get("conclusion") == "failure"]
        if names:
            failed_steps = "\n".join(f"- {n}" for n in names)
    except Exception as e:
        print(f"WARN không lấy được step fail: {e}", file=sys.stderr)
    logs = "(không lấy được log)"
    try:
        out = _gh(["run", "view", run_id, "--repo", repo, "--log-failed"])
        if out.strip():
            logs = out[-LOG_TAIL:]
    except Exception as e:
        print(f"WARN không lấy được log: {e}", file=sys.stderr)
    return failed_steps, logs


def build_prompt(repo: str, branch: str, run_id: str, run_url: str,
                 workflow: str, job_label: str,
                 failed_steps: str, logs: str) -> str:
    return f"""Bạn là agent tự động xử lý sự cố CI cho repo {repo} (branch {branch}).

Workflow "{workflow}" vừa THẤT BẠI.
- Run: {run_url} (run id: {run_id})
- Job: {job_label}
- Các step bị fail:
{failed_steps}

Log lỗi (phần cuối):
```
{logs}
```

Nhiệm vụ (làm tuần tự):
1. Clone repo, checkout {branch}, đọc AGENTS.md nếu có để nắm bối cảnh vận hành.
2. Chẩn đoán nguyên nhân gốc từ log trên; nếu cần thêm log: `gh run view {run_id} --repo {repo} --log-failed`.
3. Nếu lỗi TẠM THỜI (timeout mạng, HTTP 502/503, rate limit dịch vụ ngoài, Render cold start, site nguồn chặn scrape thoáng qua): KHÔNG sửa code — chỉ rerun `gh run rerun {run_id} --repo {repo} --failed` rồi báo cáo.
4. Nếu lỗi do CODE/CONFIG: sửa tối thiểu đúng nguyên nhân, chạy test liên quan, tạo branch `fix/auto-remediate-{run_id}`, push, mở Pull Request (KHÔNG merge) mô tả nguyên nhân + cách sửa. Trước khi mở PR, kiểm tra không trùng PR đang mở xử lý cùng lỗi.
5. TUYỆT ĐỐI KHÔNG: tự merge PR, push thẳng lên {branch}, thay đổi/xoá secrets, tắt workflow.
6. Kết thúc bằng báo cáo ngắn (tiếng Việt): nguyên nhân gốc, hành động đã làm, link PR nếu có."""


def _get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if body else {}


def start_openhands_session(api_key: str, repo: str, branch: str,
                            prompt: str, title: str) -> str | None:
    """Mở conversation trên OpenHands Cloud, trả về URL session (best effort)."""
    auth = {"Authorization": f"Bearer {api_key}"}
    st, body = _post(
        f"{OH_BASE}/api/v1/app-conversations",
        {"initial_message": {"content": [{"type": "text", "text": prompt}]},
         "selected_repository": repo, "selected_branch": branch, "title": title},
        auth)
    print(f"OpenHands start: HTTP {st}")
    conv_id = body.get("app_conversation_id")
    task_id = body.get("id")
    deadline = time.time() + 120
    while not conv_id and task_id and time.time() < deadline:
        time.sleep(10)
        tasks = _get(f"{OH_BASE}/api/v1/app-conversations/start-tasks?ids={task_id}", auth)
        items = tasks.get("items") if isinstance(tasks, dict) else None
        for t in items or [tasks]:
            if isinstance(t, dict) and t.get("app_conversation_id"):
                conv_id = t["app_conversation_id"]
                break
    return f"{OH_BASE}/conversations/{conv_id}" if conv_id else None


def notify(msg: str) -> None:
    results = []
    token, chat = os.environ.get("TELEGRAM_DONE_BOT_TOKEN", ""), os.environ.get("TELEGRAM_DONE_CHAT_ID", "")
    if token and chat:
        try:
            st, _ = _post(f"https://api.telegram.org/bot{token}/sendMessage",
                          {"chat_id": chat, "text": msg})
            results.append(f"Telegram {st}")
        except Exception as e:
            results.append(f"Telegram lỗi: {e}")
    dc_token, dc_ch = os.environ.get("DISCORD_DONE_BOT_TOKEN", ""), os.environ.get("DISCORD_DONE_CHANNEL_ID", "")
    if dc_token and dc_ch:
        try:
            st, _ = _post(f"https://discord.com/api/v10/channels/{dc_ch}/messages",
                          {"content": msg, "allowed_mentions": {"parse": []}},
                          {"Authorization": f"Bot {dc_token}"})
            results.append(f"Discord {st}")
        except Exception as e:
            results.append(f"Discord lỗi: {e}")
    print("auto-remediate notify:", "; ".join(results) or "SKIP(thiếu env)")


def main() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    run_url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{run_id}"
    workflow = os.environ.get("GITHUB_WORKFLOW", "?")
    job_label = os.environ.get("JOB_LABEL", workflow)
    branch = os.environ.get("REMEDIATE_BRANCH", "main")

    failed_steps, logs = collect_failure_info(repo, run_id)
    prompt = build_prompt(repo, branch, run_id, run_url, workflow, job_label,
                          failed_steps, logs)
    if os.environ.get("DRY_RUN") == "1":
        print("=== DRY RUN — prompt gửi OpenHands ===")
        print(prompt)
        return

    api_key = os.environ.get("OPENHANDS_API_KEY", "")
    if not api_key:
        print("SKIP: thiếu OPENHANDS_API_KEY")
        return

    now_vn = datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y %H:%M")
    title = f"Auto-remediate: {repo.split('/')[-1]} run {run_id}"
    try:
        conv_url = start_openhands_session(api_key, repo, branch, prompt, title)
    except Exception as e:
        print(f"WARN không mở được session OpenHands: {e}", file=sys.stderr)
        conv_url = None

    msg = (f"🤖 AUTO-REMEDIATION {now_vn} (giờ VN)\n"
           f"Job «{job_label}» thất bại → đã mở session OpenHands tự chẩn đoán + xử lý.\n"
           f"Run: {run_url}\n")
    msg += f"Session: {conv_url}" if conv_url else \
        "⚠️ Không lấy được link session — kiểm tra https://app.all-hands.dev"
    notify(msg)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"WARN auto_remediate lỗi: {type(e).__name__}: {e}", file=sys.stderr)
