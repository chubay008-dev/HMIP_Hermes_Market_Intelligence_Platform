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

# Chạy test (37 file; hiện 268 pass / 0 fail)
python -m pytest                        # toàn bộ + coverage gate 80%
python -m pytest extensions/tests       # test lớp web (58 pass / 1 skip)
python -m pytest extensions/tests/test_pi.py --no-cov  # test PI nhanh
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
  - `api.py` — FastAPI (tất cả endpoint `/api/*`), lifespan seed PI
  - `db.py` — SQLite lịch sử giá (path: `HMIP_DB_PATH`)
  - `pi/` — Price Intelligence (DB riêng `HMIP_PI_DB_PATH`, schema đầy đủ)
    - `collectors.py` — `collect_realtime_smart` (delegate sang `collect_smart` 4-tier chain)
    - `persistent_collector.py` — `has_real_prices` (marker), `store_price_point_if_changed` (incremental), `collect_smart` (4-tier chain)
    - `price_extract.py` — `extract_product_price(brand=)` dùng chung: filter hotline garbage + brand matching
    - `firecrawl_collector.py` (tier 1), `scraperapi_collector.py` (tier 2), `zenrows_collector.py` (tier 3), `jina_collector.py` (tier 4)
    - `service.py` — orchestration; `mark_ready` đã sửa `global _seed_state`
    - `pi_store.py` — đã thêm cột `metadata` cho `pi_skus` (marker)
  - `run_workflow.py` — NỐI kernel vào runtime thật (fix F-01)
  - `collect_adapters.py` — adapter giá (demo/http/Tiki 3 tầng — legacy, riêng PI dùng chain smart)
  - `auth.py` — Bearer token middleware
- **`domains/beer/pricing/`** — vertical slice PRC-001 (7 task: collect→extract→validate→enrich→compare→decide→alert)
- **`knowledge/master/*.json`** — master data (Brand/Product/SKU). Đã chuyển sang tên tiếng Việt.

## Thu thập giá thật (PI) — chain 4 tầng

Thứ tự fallback: **Firecrawl → ScraperAPI → ZenRows → Jina** (→ Crawl4AI tier 5 nếu `CRAWL4AI_ENABLED`).

- **Circuit breaker Firecrawl:** khi API trả 402 (hết credit), `FirecrawlCollector._credit_exhausted=True` → các SP còn lại trong run skip Firecrawl ngay (0s thay vì 60s timeout mỗi SP), xuống ScraperAPI/ZenRows/Jina. Flag reset khi nhận 200 lại (credit refresh) hoặc process restart.
- **Firecrawl credit schedule:** key `fc-abc42...` refresh credit định kỳ (kỳ tới ~14/09). Trong khi chờ, auto-scan incremental (`HMIP_PI_COLLECT_MIN=360` = 6h) dùng ScraperAPI/ZenRows/Jina. Chỉ ghi observation + notify khi giá **thay đổi** (noise threshold 1%); giá không đổi → skip (không re-seed toàn bộ).
- **Notify:** `notifier.py` gửi alert Telegram (`TELEGRAM_HMIP_MARKET_BOT` + `TELEGRAM_CHAT_ID`) + Discord (`DISCORD_BOT_TOKEN` + `DISCORD_HOME_CHANNEL` hoặc `DISCORD_DM_USER_ID` để DM trực tiếp tới user). Chỉ trigger khi `store_price_point_if_changed` phát hiện giá đổi.

- `collect_smart(limit, path)` trong `persistent_collector.py` thử từng tier cho toàn bộ sản phẩm.
- Tier thành công khi: thu được ≥1 observation mới (`collected>0`) HOẶC có giá không đổi (`skipped>0`, tức tier lấy được giá nhưng không cần ghi lại). Chỉ xuống tier sau khi cả hai đều 0.
- **One-time seed:** `has_real_prices()` kiểm marker `real_price_seeded=true` trong `pi_skus.metadata`. Seed 1 lần → marker đặt → không re-seed synthetic nữa.
- **Incremental:** `store_price_point_if_changed` chỉ ghi observation khi giá mới (ngoài noise threshold). Giá không đổi → skip (không ghi đè).
- **Lọc rác:** `extract_product_price(html, brand)` — loại token hotline ("1000 đ/phút"), chỉ nhận 5k-2tr; brand matching ưu tiên giá gần tên thương hiệu (tránh median sản phẩm khác).
- Env: `FIRECRAWL_API_KEY`, `SCRAPERAPI_KEY`, `ZENROWS_KEY` (Render: `sync: false`). Code đọc `SCRAPERAPI_KEY`/`ZENROWS_KEY` (không phải `_API_KEY`).

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
- ~~Test fail hiện tại (11): do `knowledge/master/*.json` đổi tên "Saigon Beer"→"Bia Sài Gòn" nhưng test vẫn assert tên cũ.~~ **ĐÃ SỬA (2026-08-16):** đồng bộ mock collect adapter (`collect_price.py`) + assertion trong `tests/unit/test_ontology.py`, `domains/beer/pricing/tests/test_enrich_price.py`, `domains/beer/pricing/tests/test_skills.py`, và golden dataset (`tests/prompt/golden/extract_price_golden.json`) sang "Bia Sài Gòn" khớp master data. Full suite 268 pass / 0 fail.
- Test PI (`extensions/tests/test_pi.py`) cần có thể seed DB — chạy trong tmp.

## Cấu hình & env

- Config: `config/{runtime,logging,deployment}.yaml`, mở rộng `${VAR:-default}`, freeze bất biến.
- DB paths: `HMIP_DB_PATH` (mặc định `hmip.db`), `HMIP_PI_DB_PATH` (mặc định `hmip_pi.db`).
- Auth: `HMIP_API_TOKEN` (đơn) hoặc `HMIP_API_TOKENS` (JSON array). Không set = auth tắt (dev mode).
- Thu thập giá: `HMIP_COLLECT_MODE` (demo|http). `http` mà không set `HMIP_PRICE_API_BASE` → fallback Tiki API.
- Chain smart PI: `FIRECRAWL_API_KEY`, `SCRAPERAPI_KEY`, `ZENROWS_KEY` (Render `sync: false`).
- Scheduler: `HMIP_AUTOSCAN=on`, `HMIP_SCAN_INTERVAL_MIN`, `HMIP_PI_COLLECT_MIN`.
- Xem `.env.example` cho danh sách đầy đủ (ghi rõ biến nào đã/ chưa nối code).

### Render API — CẨN TRỌNG

- 🔴 **`PUT /v1/services/{id}/env-vars` REPLACE toàn bộ env vars** (không phải upsert). Nếu body chỉ có 2 vars → mọi var khác (telegram, discord, firecrawl, scraperapi, collect_mode...) BỊ XÓA. Phải gửi TẤT CẢ env vars trong 1 PUT, hoặc dùng PATCH/upsert từng var. Xem commit 04ad580 (sửa hậu quả).
- **Postgres connection string**: dùng **pooler** hostname (`aws-0-{region}.pooler.supabase.com:6543`, user `postgres.{ref}`) — direct hostname `db.{ref}.supabase.co:5432` KHÔNG resolve DNS trên Render/Sandbox (IPv6/network). Pooler resolve OK + connection pooling.
- **`executescript` Postgres**: không forward-reference FK trong cùng script. `db_backend.py` bỏ clause `FOREIGN KEY ... REFERENCES ...` (kèm comma) + inline `REFERENCES xxx(...)` (giữ column type). Thứ tự regex quan trọng: clause riêng trước, inline sau.
- **`nonZeroExit:3`** trên Render = health check fail (grace 60s + retry) HOẶC app crash runtime. Build succeeded ≠ runtime OK.

## Bảo mật — CẨN TRỌNG

- 🔴 ~~`render.yaml` hardcode `FIRECRAWL_API_KEY` thật~~ — **ĐÃ SỬA** (đổi sang `sync: false`). Nhưng key cũ (`fc-906d...`) đã nằm trong git history (commit `32335cb`) → **vẫn cần thu hồi key đó trên Firecrawl Dashboard và sinh key mới**, vì xoá khỏi working tree không xoá khỏi history. Xem `docs/CODEBASE_OVERVIEW.md` mục 20.
- `docker-compose.yml` token mặc định `changeme-in-production` — phải đổi khi deploy.
- Dashboard `/`, `/pi`, `/workspace` + `/docs` exempt khỏi auth → lộ khi public.
- ~~`logging.yaml` khai báo `redact_fields` nhưng không có logic redact (giả).~~ **ĐÃ SỬA (2026-08-16):** `core/observability.py` thêm `make_redact_processor` + `_redact_value` (đệ quy dict/list/tuple) → structlog processor redact giá trị các key nhạy cảm (`password`/`token`/`secret`/`api_key`). `core/bootstrap.py::_initialize_logging` wire `config.logging.redact_fields` vào processor. Override qua env `HMIP_LOG_REDACT_FIELDS` (comma-separated). Test: `tests/unit/test_observability_redact.py` (7 test). Lưu ý: chỉ redact qua structlog (core runtime); extensions/ dùng stdlib `logging` riêng, chưa qua processor này.
- ~~Lineage ghi nguyên payload không lọc.~~ **ĐÃ SỬA (2026-08-16):** `core/lineage.py` thêm `_scrub_payload` (dùng `_redact_value` từ observability) → cả `InMemoryLineageTracer` và `PersistentLineageTracer` redact sensitive keys (`password`/`token`/`secret`/`api_key`, đệ quy nested) trước khi ghi, tuân thủ `05_Interface_Contract.md §4.8` "Không ghi secret plaintext". Mặc định BẬT; truyền `redact_fields=None` để disable (test exact payload). Test: `tests/unit/test_lineage.py` (4 test redact mới).
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
- **ĐỒNG BỘ `DEFAULT_PRODUCTS` ↔ `knowledge/master/*.json` (quan trọng):** Khi thêm SP vào `DEFAULT_PRODUCTS`, PHẢI thêm entry tương ứng vào `products.json` (id/brand_id/name/category) + `brands.json` (id/name) + `skus.json`. Nếu không, task `enrich` (enrich_price.py) raise `ENRICH_PRICE_UNKNOWN_PRODUCT` → workflow FAILED → UI "chọn SP quét báo lỗi". `sync_to_ontology` (db.py) chỉ chạy khi user thêm SP mới từ UI (POST /api/products), không tự chạy cho SP có sẵn trong `DEFAULT_PRODUCTS`. Đã fix 1 lần (2026-08): thêm 24 SP thiếu + sửa brand mismatch P333 (Larue→Bia Larue). Lỗi tái diễn nếu `DEFAULT_PRODUCTS` có SP chưa có trong master.
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
