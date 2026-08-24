# HMIP — Documentation Index

Dự án hoàn thành 2026-08-04. File này là điểm bắt đầu khi quay lại dự
án — đọc theo đúng thứ tự dưới đây.

## 1. Đọc trước tiên khi quay lại dự án

| File | Nội dung |
|---|---|
| `OPEN_QUESTIONS_RESOLVED.md` | Trạng thái mới nhất của mọi quyết định kiến trúc từng bỏ ngỏ — **đọc file này trước**, không đọc các SPRINT_*_STATUS.md như nguồn "sự thật hiện tại" (chúng là nhật ký lịch sử, có thể chứa giá trị đã bị thay đổi sau đó). |
| `ADR_010_platform_package_rename.md` | Quyết định đổi `platform/` → `platform_/` (xung đột tên với module chuẩn Python) — ảnh hưởng mọi lệnh chạy CLI/Docker. |

## 2. Tài liệu đặc tả gốc của dự án (không do Claude tạo)

21 file `01_..._20_...md` + `master_documentation_pack.md` + `README.md`
ở gốc dự án — bộ đặc tả kiến trúc/domain/interface/data contract gốc.
Đáng chú ý nhất khi cần tra lại:

- `05_Interface_Contract.md` — mọi protocol/exception class đã khóa cứng (Registry, EventBus, ConfigLoader, Planner, BaseAdapter, BaseSkill, WorkflowEngine, DecisionEngine, LineageTracer).
- `12_Data_Contract.md` — shape dữ liệu (BeerPrice, TaskExecutionResult, BootstrapReport, LineageRecord...).
- `14_Repository_File_Mapping.md` — cấu trúc thư mục dự kiến (lưu ý: `platform/` trong tài liệu này đã đổi tên thật thành `platform_/`, xem ADR-010).
- `10_Project_Backlog.md` / `15_Acceptance_Criteria.md` — phạm vi + tiêu chí từng sprint.

## 3. Nhật ký triển khai theo sprint (lịch sử — không sửa lại)

| File | Sprint | Nội dung chính |
|---|---|---|
| `SPRINT_1_STATUS.md` | 1 | Foundation: bootstrap, context, registry, config skeleton. |
| `SPRINT_2_STATUS.md` | 2 | Runtime Core: workflow, planner, event bus, executor. |
| `SPRINT_3_STATUS.md` | Retrofit | Khớp lại toàn bộ `core/` đúng `05_Interface_Contract.md` (3 vòng, gồm quyết định "raise đúng class"). |
| `SPRINT_3_PRC001_STATUS.md` | 3 | Vertical slice PRC-001 thật (BaseAdapter/BaseSkill/DecisionEngine). |
| `SPRINT_4_STATUS.md` | 4 | Knowledge Layer (ontology Brand/Product/SKU) + Lineage persistence. |
| `SPRINT_5_STATUS.md` | 5 | Coverage gate, chaos test, golden dataset, compensation orchestration. |
| `SPRINT_6_STATUS.md` | 6 | Docker, health/readiness, deployment manifests — **và sự cố đặt tên `platform/` bùng phát thật** (xem ADR-010). |

## 4. Vận hành / triển khai

| File | Nội dung |
|---|---|
| `Dockerfile`, `.dockerignore` | Build image (Python 3.12, pin theo ADR-009). |
| `deployment/docker-compose.yml` | Chạy local. |
| `deployment/kubernetes/{job,configmap}.yaml` | Triển khai K8s (Job, không phải Deployment — không có HTTP server). |
| `deployment/RELEASE_CHECKLIST.md` | Quy trình release 6 bước, có mục "known gaps" thật thà. |
| `.env.example` | Toàn bộ biến môi trường, mỗi biến ghi rõ đã nối vào code hay chỉ mới khai báo. |
| `config/{runtime,logging,deployment}.yaml` | Config runtime thật, do `platform_/bootstrap.py` nạp. |
| `docs/CODEBASE_OVERVIEW.md` §11–11c | **Lịch automation + Daily Intelligence Report**: scheduler Render + GitHub Actions (3 mốc) + `hmip_daily_report` (CronTrigger 00:00 UTC = 07:00 VN, PR #20); §12 bảng env đầy đủ (`HMIP_DAILY_REPORT*`). |
| `AGENTS.md` "Tự động hằng ngày — tổng hợp lịch" | Tóm tắt tay trái (giờ VN) + ghi chú CronTrigger động trong Render (trang handler của report). |

## Kiểm thử và xác nhận của tôi (27/08/2026)
- `extensions/tests/test_pi_daily_report.py` — 9/9 pass.
- `extensions/tests` — 145 pass + 1 skip; `tests/` — 236 pass (kernel).
- `ruff` sạch tất cả file mới/sửa; `mypy` sạch `extensions/pi/report_engine.py`.

## 5. Code — điểm vào quan trọng

| Thứ cần tìm | Ở đâu |
|---|---|
| Bootstrap chạy toàn hệ thống | `platform_/bootstrap.py` (`python -m platform_.bootstrap`) |
| Health/readiness check | `platform_/health.py`, `platform_/readiness.py` |
| Chạy 1 workflow end-to-end | `core/workflow_engine.py::WorkflowEngine` |
| Vertical slice PRC-001 thật | `domains/beer/pricing/` (`registrar.py` là điểm nối tất cả handler) |
| Workflow PRC-001 (YAML) | `domains/beer/pricing/workflows/WF-PRC-001.yaml` — 7 task: collect→extract→validate→enrich→compare→decide→alert |
| Ontology + master data | `knowledge/ontology/`, `knowledge/master/*.json` |
| Toàn bộ exception class khóa cứng | `core/exceptions.py` |

## 6. Test — điểm vào quan trọng

| Loại test | Ở đâu |
|---|---|
| Unit test core/domain | `tests/unit/`, `domains/beer/pricing/tests/` |
| End-to-end PRC-001 thật | `tests/workflow/test_prc_001_end_to_end.py` |
| Regression (bug lịch sử) | `tests/workflow/test_prc_001_regression.py` |
| Compensation/rollback | `tests/workflow/test_prc_001_compensation.py` |
| Chaos/fault injection | `tests/chaos/` |
| Golden dataset (extraction/decision) | `tests/prompt/`, `tests/prompt/golden/*.json` |

Chạy full suite: `uv run ruff check . && uv run mypy . && uv run pytest -v`
(coverage gate 80% chung + có thể chạy riêng gate 90% cho critical path — xem `SPRINT_5_STATUS.md`).

## 7. Việc còn lại nếu quay lại dự án (không chặn, không bắt buộc)

- Build Docker thật chưa được xác nhận chạy (`docker build -t hmip:dev .`).
- Chưa có LLM thật cho extraction (đang deterministic — xem `SPRINT_3_PRC001_STATUS.md`).
- Chưa có adapter HTTP thật cho collect (đang mock — xem `domains/beer/pricing/skills/collect_price.py`).
- ~~Chưa có CI pipeline file.~~ **Đã thêm (2026-08-16):** `.github/workflows/ci.yml` — ruff (kernel+tests) + mypy strict (kernel) + pytest (coverage gate 80%). **Đã xanh qua PR #12 (#53845ab) + PR #13 (#02fa68c, 415 pass / 1 skip, coverage 94.28%)** (2026-08-17).
- ~~Chưa có secret provider thật~~ (`HMIP_SECRET_PROVIDER` mới chỉ là placeholder) — vẫn mở.
- ~~Lỗi hiển thị giá sai trong tin nhắn cảnh báo~~ (pack-mismatch `-98.67%` giả, "Giá thùng (450 lon)") — **ĐÃ SỬA (PR #13, 2026-08-17):** so sánh + alert trên giá/LON, clamp pack `{6,12,24}`, "Giá thùng (24 lon)" cố định. Xem `AGENTS.md` mục "Thu thập giá thật (PI)" + "Hai hệ thống notify".
