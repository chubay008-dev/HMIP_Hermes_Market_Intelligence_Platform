# HMIP Architecture Documentation

Bộ tài liệu này được sinh theo quy trình **Hermes Codebase Architecture Discovery & Documentation Workflow** (4 phase: Inventory → Architecture Trace → Verification → Documentation).

Nguyên tắc áp dụng: mọi claim quan trọng đều có source evidence (file + symbol); không có evidence thì đánh dấu `[INFERRED]` hoặc `[UNKNOWN]`; mâu thuẫn được báo cáo chứ không tự chọn một bên; không sửa source code trong quá trình discovery.

## Đọc theo thứ tự nào

| # | Tài liệu | Dành cho |
|---|---|---|
| 1 | [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) | Người mới — HMIP là gì, khởi động ra sao |
| 2 | [ARCHITECTURE.md](ARCHITECTURE.md) | Kiến trúc thực tế + Mermaid diagram + giới hạn |
| 3 | **[VERIFICATION_REPORT.md](VERIFICATION_REPORT.md)** | **Quan trọng nhất** — findings, contradictions, khuyến nghị |
| 4 | [CODEBASE_INVENTORY.md](CODEBASE_INVENTORY.md) | Bản đồ repository (Phase 1) |
| 5 | [MODULES.md](MODULES.md) | Chi tiết từng module |
| 6 | [DATA_FLOW.md](DATA_FLOW.md) | 4 flow dữ liệu |
| 7 | [API.md](API.md) · [DATABASE.md](DATABASE.md) · [INTEGRATIONS.md](INTEGRATIONS.md) | Bề mặt ngoài (đều gần như trống — có lý do) |
| 8 | [CONFIGURATION.md](CONFIGURATION.md) · [DEPLOYMENT.md](DEPLOYMENT.md) · [SECURITY.md](SECURITY.md) | Vận hành |
| 9 | [TESTING.md](TESTING.md) · [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Phát triển hằng ngày |

## Tóm tắt 30 giây

HMIP là **runtime kernel điều phối workflow DAG**, đóng gói thành CLI chạy-rồi-thoát (K8s Job), với một domain slice duy nhất là PRC-001 (giá bia). Không HTTP server, không database, không external integration. 268 test pass, coverage 94%.

**Khoảng cách lớn nhất giữa giấy tờ và thực tế:** `WorkflowEngine` chỉ được gọi từ test — container production chỉ chạy bootstrap rồi thoát, WF-PRC-001 không bao giờ thực thi. Chi tiết ở F-01.

## Cách xác minh

Bộ tài liệu này dựa trên thực thi thật, không chỉ đọc code:

```bash
python3 -m venv /tmp/hmip-venv && /tmp/hmip-venv/bin/pip install -e ".[dev]"
/tmp/hmip-venv/bin/python -m pytest -q                    # 268 passed, 94.07%
/tmp/hmip-venv/bin/python -m platform_.bootstrap          # exit 0, steps=8
/tmp/hmip-venv/bin/python -m platform_.health             # HEALTHY
/tmp/hmip-venv/bin/python -m platform_.readiness          # READY
```

## Quy trình cập nhật (mục 31-32 của workflow)

Không chạy lại toàn bộ 4 phase mỗi lần. Khi code đổi:

```text
git diff → file thay đổi → module bị ảnh hưởng → verify lại phần đó → cập nhật doc liên quan → human review
```

Ví dụ: sửa `domains/beer/pricing/` thì chỉ cần kiểm lại MODULES.md, DATA_FLOW.md (Flow 3), ARCHITECTURE.md mục 4-5.

## Trạng thái

```text
Repository Discovery       → COMPLETE
Architecture Analysis      → COMPLETE
Source Verification        → COMPLETE  (chạy thật, không chỉ đọc)
Documentation              → COMPLETE
Security Sanitization      → COMPLETE  (không giá trị secret nào trong docs)
Human Review               → PENDING   ← cần bạn xác nhận F-01..F-08
```

Theo mục 33 của workflow, human review nên tập trung vào: F-01 (workflow chưa được nối vào entrypoint), F-04/R-01 (logging & redaction chưa có hiệu lực), F-03 (ngữ nghĩa persistence khác nhau giữa compose và K8s).
