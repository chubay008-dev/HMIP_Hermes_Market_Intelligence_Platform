# AGENTS.md — HMIP (Hermes Market Intelligence Platform)

> Bộ nhớ bền vững cho agent (OpenHands) khi làm việc với kho mã này.
> Đọc file này đầu mỗi phiên. Cập nhật khi có insight quan trọng.
> Xem thêm: `docs/CODEBASE_OVERVIEW.md` (phân tích kiến trúc chi tiết), `INDEX.md` (điểm vào tài liệu).

## Bản tóm tắt nhanh

HMIP là platform giám sát giá bia Việt Nam + workflow engine (AI OS). Hai lớp tồn tại song song:
- **Kernel gốc** (`core/`, `domains/`, `knowledge/`, `platform_/`): run-to-completion, không có web/DB. Mô tả đúng trong `docs/ARCHITECTURE.md`.
- **Lớp web/extensions** (`extensions/`): FastAPI + SQLite + scheduler + collector giá thật + Price Intelligence module. Đây là **app thực tế** mà người dùng chạy.

⚠️ **Tài liệu `docs/DATABASE.md`, `docs/API.md`, `docs/INTEGRATIONS.md`, `docs/SECURITY.md` đã LỖI THỜI** — mô tả kernel gốc (Sprint 1-6), không phản ánh lớp `extensions/`. Dùng `docs/CODEBASE_OVERVIEW.md` cho trạng thái hiện tại.

## Lệnh phổ biến

```bash
# Chạy web app (local) — tự tạo venv, cài deps, chạy uvicorn
./start.sh                              # http://127.0.0.1:8000

# Cài deps cho dev/test
pip install -e ".[dev]"
pip install fastapi "uvicorn[standard]" apscheduler httpx requests

# Chạy test (37 file; hiện 257 pass / 11 fail — fail do mismatch data, xem phần Technical Debt)
python -m pytest                        # toàn bộ + coverage gate 80%
python -m pytest extensions/tests       # test lớp web
python -m pytest tests/workflow         # test PRC-001 end-to-end
python -m pytest -p no:cov --no-cov     # chạy nhanh không coverage

# Lint/type-check
ruff check .
mypy .                                  # strict, exclude tests/

# CLI kernel (run-to-completion, không web)
python -m platform_.bootstrap           # bootstrap rồi thoát
python -m platform_.health              # health check (exit-code)
python -m platform_.readiness           # readiness check

# Chạy 1 workflow
python -m extensions.run_workflow P123 demo

# Scheduler độc lập
python -m extensions.scheduler
```

## Cấu trúc quan trọng

- **`core/`** — kernel runtime. KHÔNG sửa trừ khi đổi contract (phải cập nhật `05_Interface_Contract.md`). Không import `domains/`.
- **`extensions/`** — lớp web + tích hợp. Đây là nơi thêm tính năng ứng dụng mà không phá kernel.
  - `api.py` — FastAPI (tất cả endpoint `/api/*`)
  - `db.py` — SQLite lịch sử giá (path: `HMIP_DB_PATH`)
  - `pi/` — Price Intelligence (DB riêng `HMIP_PI_DB_PATH`, schema đầy đủ)
  - `run_workflow.py` — NỐI kernel vào runtime thật (fix F-01)
  - `collect_adapters.py` — adapter giá (demo/http/Tiki 3 tầng)
  - `auth.py` — Bearer token middleware
- **`domains/beer/pricing/`** — vertical slice PRC-001 (7 task: collect→extract→validate→enrich→compare→decide→alert)
- **`knowledge/master/*.json``** — master data (Brand/Product/SKU). Đã chuyển sang tên tiếng Việt.

## Quy ước mã nguồn

- Python ≥3.12. Docstring khóa shape theo `05_Interface_Contract.md` / `12_Data_Contract.md`.
- Exception: dùng đúng class locked + `.code` attribute để phân biệt (KHÔNG tạo subclass). Xem `core/exceptions.py`.
- Lỗi nghiệp vụ task: **không raise**, trả `TaskExecutionResult(FAILED)`. Lỗi cấu trúc/infra: raise.
- `yaml.safe_load` ở mọi nơi. Không `eval`/`exec`/`shell=True`.
- Lint: ruff (`E,F,I,UP,B`), line-length 100. mypy strict (exclude tests/).
- Coverage: ≥80% (unit, tự động), ≥90% (workflow, review thủ công).
- Tiếng Việt dùng trong comment/docstring/message là bình thường (dự án Việt Nam).

## Kiểm thử

- `tests/conftest.py` thêm repo root vào `sys.path` (không cần editable install để import).
- Test fail hiện tại (11): do `knowledge/master/*.json` đổi tên "Saigon Beer"→"Bia Sài Gòn" nhưng test vẫn assert tên cũ. **Đây là nợ kỹ thuật, không phải regression của app.** Khi sửa, cập nhật assertion trong `tests/unit/test_ontology.py`, `domains/beer/pricing/tests/test_enrich_price.py`, `tests/workflow/test_prc_001_*.py`.
- Test PI (`extensions/tests/test_pi.py`) cần có thể seed DB — chạy trong tmp.

## Cấu hình & env

- Config: `config/{runtime,logging,deployment}.yaml`, mở rộng `${VAR:-default}`, freeze bất biến.
- DB paths: `HMIP_DB_PATH` (mặc định `hmip.db`), `HMIP_PI_DB_PATH` (mặc định `hmip_pi.db`).
- Auth: `HMIP_API_TOKEN` (đơn) hoặc `HMIP_API_TOKENS` (JSON array). Không set = auth tắt (dev mode).
- Thu thập giá: `HMIP_COLLECT_MODE` (demo|http). `http` mà không set `HMIP_PRICE_API_BASE` → fallback Tiki API.
- Scheduler: `HMIP_AUTOSCAN=on`, `HMIP_SCAN_INTERVAL_MIN`, `HMIP_PI_COLLECT_MIN`.
- Xem `.env.example` cho danh sách đầy đủ (ghi rõ biến nào đã/ chưa nối code).

## Bảo mật — CẨN TRỌNG

- 🔴 ~~`render.yaml` hardcode `FIRECRAWL_API_KEY` thật~~ — **ĐÃ SỬA** (đổi sang `sync: false`). Nhưng key cũ (`fc-906d...`) đã nằm trong git history (commit `32335cb`) → **vẫn cần thu hồi key đó trên Firecrawl Dashboard và sinh key mới**, vì xoá khỏi working tree không xoá khỏi history. Xem `docs/CODEBASE_OVERVIEW.md` mục 20.
- `docker-compose.yml` token mặc định `changeme-in-production` — phải đổi khi deploy.
- Dashboard `/`, `/pi`, `/workspace` + `/docs` exempt khỏi auth → lộ khi public.
- `logging.yaml` khai báo `redact_fields` nhưng không có logic redact (giả).
- Lineage ghi nguyên payload không lọc.
- Khi sửa auth: route exempt nằm trong `_EXEMPT_EXACT`/`_EXEMPT_PREFIX` trong `extensions/auth.py`.

## Kiến trúc — lưu ý dễ nhầm

- **Hai mô hình runtime:** `platform_/bootstrap` (CLI run-to-completion, K8s Job) vs `extensions/api` (web server, port 8000). Cả hai đều tồn tại. Đừng nhầm.
- `WorkflowEngine.cancel()` vô hiệu (execute đồng bộ, tự sinh execution_id).
- Compensation: cơ chế thật nhưng toàn no-op (chưa có side effect thật cần hoàn tác).
- `WorkflowEngine` mặc định `InMemoryLineageTracer`; `run_workflow.py` inject dual (persistent + memory).
- `platform_` có dấu gạch chân vì trùng tên stdlib `platform` (ADR-010).

## Khi sửa đổi — nguyên tắc

- **Thêm tính năng ứng dụng:** sửa `extensions/` (web/PI/db/adapter). KHÔNG sửa `core/` trừ khi thật cần.
- **Thêm domain mới:** theo mẫu `domains/<domain>/<subdomain>/` (registrar + skills + workflow YAML + decision_engine).
- **Thêm sản phẩm giám sát:** cập nhật `extensions/default_products.py` (`DEFAULT_PRODUCTS`) + `extensions/run_workflow.py` (`_BASE_PRICES`). UI thêm SP tự sync vào ontology qua `db.sync_to_ontology`.
- **Đổi contract kernel:** cập nhật `05_Interface_Contract.md` + `12_Data_Contract.md` trước.
- **Đừng tạo file mới trùng tên/phiên bản** — sửa file gốc trực tiếp.

## Tài liệu tham chiếu (ưu tiên đọc theo thứ tự)

1. `INDEX.md` — điểm bắt đầu khi quay lại dự án
2. `OPEN_QUESTIONS_RESOLVED.md` — trạng thái mới nhất các quyết định kiến trúc (đọc trước SPRINT_*)
3. `docs/CODEBASE_OVERVIEW.md` — tổng quan kiến trúc hiện tại (file này tham chiếu)
4. `docs/ARCHITECTURE.md` — chi tiết kernel (chính xác cho core/)
5. `07_ADR.md` + `16_ADR_Details.md` — quyết định kiến trúc
6. `05_Interface_Contract.md` — protocol/exception khóa
7. `12_Data_Contract.md` — shape dữ liệu
8. `APP_README.md` — hướng dẫn dùng app thực tế
