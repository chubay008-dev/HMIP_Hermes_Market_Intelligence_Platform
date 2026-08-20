# CODEBASE OVERVIEW — HMIP (Hermes Market Intelligence Platform)

> Tài liệu tóm tắt kiến trúc toàn kho mã nguồn, tạo bằng khảo sát **chỉ đọc** mã nguồn/cấu hình/test.
> Quy ước: `[VERIFIED]` = xác nhận từ mã nguồn; `[INFERRED]` = suy luận từ cấu trúc/hành vi; `[UNKNOWN]` = không tìm thấy bằng chứng.

---

## 1. Mục đích & trách nhiệm nghiệp vụ (domain)

**Mục đích:** HMIP định vị là một **Enterprise AI Operating System** theo mô hình *single-agent autonomous* (Hermes Agent là orchestrator trung tâm). Mục tiêu: biến AI thành một runtime platform điều phối dữ liệu, tri thức, công cụ và quyết định nghiệp vụ một cách nhất quán, có thể kiểm soát và truy vết. `[VERIFIED]` — `01_System_Specification.md` mục 1, `README.md`.

**Trách nhiệm nghiệp vụ thực tế (đã hiện thực hoá):**
- **Vertical slice đầu tiên: PRC-001 — Daily Beer Price Collection** — thu thập giá bia, trích xuất, kiểm chứng schema, enrich bằng ontology, so sánh với giá tham chiếu, ra quyết định (IGNORE/ALERT/ESCALATE/HUMAN_REVIEW), và cảnh báo. `[VERIFIED]` — `README.md`, `domains/beer/pricing/`, `WF-PRC-001.yaml`.
- **Giám sát giá sản phẩm (Price Intelligence, "PI")** — dashboard phân tích giá đa kênh/đa vùng, phát hiện price event, index giá, positioning, promotion intelligence, alert, và AI Analyst (Q&A) cho thị trường bia Việt Nam. `[VERIFIED]` — `extensions/pi/`, `extensions/web/pi.html`.
- Thiết kế khuyến khích cắm thêm domain khác theo mẫu `domains/<domain>/<subdomain>/`, nhưng **chỉ có đúng 1 domain** (beer/pricing). `[INFERRED]` — cấu trúc thư mục `domains/`.

---

## 2. Ngăn xếp công nghệ (technology stack)

| Thành phần | Công nghệ | Bằng chứng |
|---|---|---|
| Ngôn ngữ | Python ≥3.12 (local dev: 3.13/3.14, container: 3.13-slim) | `pyproject.toml`, `Dockerfile` (`python:3.13-slim`), `OPEN_QUESTIONS_RESOLVED.md` mục 3 |
| Web framework | FastAPI + Uvicorn | `extensions/api.py`, `requirements.txt` |
| Validation | Pydantic v2 (API models) | `extensions/api.py` (`BaseModel`), `requirements.txt` |
| Định cấu hình | PyYAML (`yaml.safe_load`) | `core/config.py`, `requirements.txt` |
| Logging có cấu trúc | structlog (JSON) | `core/observability.py` |
| Schema validation | jsonschema | `requirements.txt`, `validate_price.py` |
| Lập lịch chạy ngầm | APScheduler | `extensions/scheduler.py`, `extensions/api.py` |
| HTTP client | httpx + requests | `requirements.txt`, `extensions/pi/collectors.py` |
| Quản lý gói (local) | uv (`uv.lock`) | `uv.lock`, `INDEX.md` |
| Kiểm thử | pytest, pytest-cov | `pyproject.toml` |
| Lint/Type-check | ruff, mypy (strict) | `pyproject.toml` |
| Persistence | SQLite (sqlite3 stdlib) | `extensions/db.py`, `extensions/pi/pi_store.py` |
| Frontend | HTML/CSS/JS thuần (single-file) | `extensions/web/*.html` |

`[VERIFIED]` cho mọi dòng (file/config tương ứng).

**Lưu ý phân kỳ phụ thuộc:** `pyproject.toml` chỉ khai báo 3 gói runtime (pyyaml, structlog, jsonschema) + dev. Các gói web (fastapi/uvicorn/apscheduler/httpx/requests) nằm riêng trong `requirements.txt` và `Dockerfile`, **không** trong `pyproject.toml` `[project].dependencies`. `[VERIFIED]`.

---

## 3. Cấu trúc kho mã nguồn

```
HMIP/
├── core/                       # Kernel runtime (KHÔNG chứa logic nghiệp vụ)
│   ├── bootstrap.py            # BootstrapKernel (8 bước chuẩn bị runtime)
│   ├── config.py               # ConfigLoader (load→merge→expand→validate→freeze)
│   ├── workflow_engine.py      # WorkflowEngine (chạy workflow end-to-end + compensation)
│   ├── workflow.py             # WorkflowLoader (parse YAML → WorkflowDefinition)
│   ├── planner.py              # Planner (DAG waves + phát hiện chu trình)
│   ├── executor.py             # TaskExecutor (chạy 1 task + retry + template resolve)
│   ├── registry.py             # TaskRegistry (state machine READY→FROZEN→...)
│   ├── event_bus.py            # EventBus (pub/sub đồng bộ)
│   ├── lineage.py              # InMemory/PersistentLineageTracer
│   ├── context.py              # ExecutionContext / Factory
│   ├── models.py              # TaskExecutionResult, BootstrapReport, DecisionResult
│   ├── exceptions.py           # Hệ exception khóa theo contract
│   └── observability.py        # structlog setup
├── platform_/                  # Lớp platform (CLI, health, readiness) — tên "platform_" do xung đột stdlib (ADR-010)
│   ├── bootstrap.py            # CLI entrypoint: python -m platform_.bootstrap
│   ├── health.py               # Health check (CLI exit-code)
│   ├── readiness.py            # Readiness marker file
│   └── diagnostics.py          # Diagnostics (Python version)
├── domains/                    # Lớp domain (vertical slice DDD)
│   └── beer/pricing/            # PRC-001
│       ├── workflows/WF-PRC-001.yaml   # Định nghĩa 7 task
│       ├── registrar.py         # Đăng ký 7 task handler vào registry
│       ├── decision_engine.py  # PricingDecisionEngine (ngưỡng 5%/10%)
│       ├── models.py
│       ├── schemas/schema.json
│       ├── prompts/extract_price.md
│       └── skills/              # 7 skill handler (collect→alert)
├── knowledge/                  # Lớp tri thức
│   ├── ontology/               # OntologyLoader, models (Brand/Product/SKU), core_schema.json
│   ├── master/                  # brands.json, products.json, skus.json (master data)
│   └── dynamic/lineage/        # lineage.jsonl (audit trail)
├── extensions/                 # Lớp web + tích hợp THẬT (không thuộc core kernel gốc)
│   ├── api.py                  # FastAPI app (lớp web bọc kernel)
│   ├── db.py                   # SQLite cho lịch sử giá giám sát
│   ├── auth.py                 # Bearer token middleware
│   ├── scheduler.py            # Quét định kỳ (APScheduler blocking)
│   ├── collect_adapters.py     # Adapter giá (demo/http/Tiki thật 3 tầng)
│   ├── run_workflow.py         # NỐI WorkflowEngine vào runtime thật (fix F-01)
│   ├── default_products.py     # Catalog bia hardcode (~48 SP)
│   ├── fake_price_api.py      # Mock server cho chế độ http test
│   ├── notifiers/telegram.py   # Cảnh báo Telegram (cho PRC-001)
│   ├── state/                  # State wrappers — ĐÓNG GÓI module-level state (refactor 2026-08-20)
│   │   ├── api_state.py        # APIState: _AUTO_SCAN_IN_PROGRESS, _AUTO_PI_COLLECT_IN_PROGRESS
│   │   ├── discord_cache.py    # DiscordChannelCache: _dm_channel_cache (dùng chung discord.py + pi/notifier.py)
│   │   ├── rate_limit_state.py # RateLimitState: _state, _state_db_path (notifiers/rate_limit.py)
│   │   ├── pi_notifier_state.py# PINotifierState: _notify_state, _sku_notify_state, _state_db_path (pi/notifier.py)
│   │   └── real_prices_cache.py# RealPricesCache: cache giá thật (chưa wire vào dùng)
│   └── pi/                     # Price Intelligence module (Spec v2.0/v3.1)
│       ├── service.py          # Orchestration + payload builder cho API
│       ├── pi_store.py         # SQLite PI (schema đầy đủ: Product/Variant/SKU/Observation/...; cột metadata cho marker)
│       ├── collectors.py       # Thu thập giá thật (Tiki API) + collect_realtime_smart (4-tier chain)
│       ├── firecrawl_collector.py  # Firecrawl Extract API (tier 1)
│       ├── scraperapi_collector.py # ScraperAPI (render JS, tier 2) — MỚI
│       ├── zenrows_collector.py    # ZenRows (js_render, tier 3) — MỚI
│       ├── jina_collector.py    # Jina Reader fallback (tier 4, filter hotline garbage)
│       ├── crawl4ai_collector.py # Crawl4AI headless (tier 5, mặc định tắt)
│       ├── price_extract.py    # extract_product_price dùng chung: filter hotline + brand matching — MỚI
│       ├── persistent_collector.py # has_real_prices marker + store_price_point_if_changed (incremental) + collect_smart — MỚI
│       ├── normalization.py    # Quy giá về per_100ml để so sánh
│       ├── analytics.py        # KPI/trend/index/positioning/channel/region/promo
│       ├── events.py           # Phát hiện price event + alert (dedup)
│       ├── seed.py             # Sinh dữ liệu thị trường mô phỏng
│       ├── ai_analyst.py       # AI Analyst (OpenRouter LLM, rule-based fallback)
│       ├── notifier.py         # Đẩy alert sang Discord + Telegram (PI)
│       ├── models.py           # Canonical data contract (PriceObservation, ...)
│       └── events.py
│   └── web/                    # Frontend single-file
│       ├── index.html          # Dashboard giám sát giá (862 dòng)
│       └── pi.html             # Price Intelligence workspace (716 dòng)
├── shared/                     # Hằng số & type dùng chung (constants, types)
├── config/                     # config/*.yaml (runtime, logging, deployment)
├── tests/                      # Test core + workflow (unit/integration/chaos/prompt/workflow)
├── deployment/                 # docker-compose, k8s (job/configmap), release checklist
├── docs/                       # Tài liệu kiến trúc (ARCHITECTURE, SECURITY, DATABASE, ...)
├── data/                       # Thư mục dữ liệu runtime (raw/normalized/...) — trống
├── reports/                    # Bootstrap report JSON (gitignored)
└── 20 file đặc tả gốc (01_.._20_..md) + SPRINT_*.md + ADR + INDEX.md
```

`[VERIFIED]` — cấu trúc từ `find`, nội dung từng file đã đọc.

---

## 4. Điểm khởi đầu (entry points)

| Điểm vào | Lệnh | Vai trò | Bằng chứng |
|---|---|---|---|
| **Web app (chính)** | `./start.sh` → `uvicorn extensions.api:app` | Khởi động FastAPI + scheduler nền + auto-seed PI | `start.sh`, `extensions/api.py` |
| **Web app (manual)** | `python -m uvicorn extensions.api:app --port 8000` | Tương đương | `api.py` docstring |
| **Bootstrap CLI (kernel)** | `python -m platform_.bootstrap` | Chạy bootstrap rồi thoát (run-to-completion) | `platform_/bootstrap.py` |
| **Workflow runner CLI** | `python -m extensions.run_workflow <product_id> [source]` | Chạy WF-PRC-001 cho 1 SP, ghi SQLite | `extensions/run_workflow.py:main` |
| **Scheduler độc lập** | `python -m extensions.scheduler` | Quét định kỳ (blocking) | `extensions/scheduler.py:main` |
| **Health check** | `python -m platform_.health` | Liveness (exit-code) | `platform_/health.py` |
| **Readiness check** | `python -m platform_.readiness` | Readiness (marker file) | `platform_/readiness.py` |
| **Fake price API** | `python extensions/fake_price_api.py` | Mock server cho chế độ http | `extensions/fake_price_api.py` |

`[VERIFIED]` cho mọi điểm vào. Lưu ý: tồn tại **hai mô hình runtime song song** — (a) kernel `platform_/bootstrap` run-to-completion (CLI) và (b) lớp web `extensions.api` (long-running server). Lớp web bọc kernel chứ không thay kernel thành server (mỗi request tạo execution độc lập). `[VERIFIED]` — `APP_README.md`, `extensions/api.py`.

---

## 5. Kiến trúc backend

**Phong cách:** Layered kernel + plugin-style domain registration, chạy **đồng bộ, đơn tiến trình**. `[VERIFIED]` — `docs/ARCHITECTURE.md` mục 1, `core/workflow_engine.py` (vòng `for` tuần tự).

**5 lớp (theo đặc tả):** Core Runtime / Domain / Knowledge / Platform / Operations. `[VERIFIED]` — `01_System_Specification.md` mục 2.

**Nguyên tắc chính:** `[VERIFIED]` — `01_System_Specification.md` mục 3:
- Kernel không chứa logic nghiệp vụ; core/ không import domains/.
- Domain cắm vào kernel qua callback `TaskRegistrar = Callable[[TaskRegistry], None]` (dependency injection qua constructor).
- Trace everything (lineage cho mỗi task).
- Immutable by default (config freeze, registry freeze).

**Workflow runtime (kernel):**
- `WorkflowEngine` tải workflow YAML → `Planner` dựng DAG wave → `TaskExecutor` chạy tuần tự các task theo wave, resolve template `${task.output}` qua dict `outputs`.
- Lỗi nghiệp vụ của task **không raise** — trả `TaskExecutionResult(FAILED)`. Lỗi cấu trúc/infra thì raise (`WorkflowParseException`/`WorkflowExecutionException`).
- Compensation (saga pattern): khi `compensation_policy: STRICT` và task fail, gọi rollback các task đã SUCCESS theo thứ tự ngược; rollback lỗi được gom lại, không chặn các rollback còn lại. `[VERIFIED]` — `core/workflow_engine.py:_compensate`.

**Lớp web (extensions/):** FastAPI bọc kernel. `/api/run` khởi tạo một execution mới mỗi lần gọi. APScheduler chạy nền cho auto-scan + thu thập giá PI. `[VERIFIED]` — `extensions/api.py`.

---

## 6. Kiến trúc frontend

**Frontend tĩnh, single-file HTML** (HTML/CSS/JS thuần, không framework build). `[VERIFIED]` — `extensions/web/index.html` (862 dòng), `extensions/web/pi.html` (716 dòng).

| Trang | Route | Nội dung |
|---|---|---|
| `index.html` | `/` (dashboard giám sát) | Bảng giá mới nhất, lịch sử, biểu đồ, cảnh báo, auto-scan, thêm sản phẩm, login token |
| `pi.html` | `/pi`, `/workspace` | Price Intelligence workspace: KPI, trend, index, positioning, channel/region, promotions, events, alerts, AI analyst |

- Giao tiếp với backend qua `fetch()` tới `/api/*`. Có dark/light theme (CSS variables). `[VERIFIED]`.
- Có form login nhập `HMIP_API_TOKEN`, lưu localStorage. `[INFERRED]` từ `DEPLOY.md` mục 4 + `extensions/auth.py`.
- Phục vụ qua `StaticFiles` mount tại `/static` và `FileResponse` cho `/`, `/pi`, `/workspace`. `[VERIFIED]` — `extensions/api.py` cuối file.

---

## 7. Lớp API

**HTTP API (FastAPI):** `[VERIFIED]` — `extensions/api.py`. Version app: 1.2.0.

**Nhóm endpoint:**

*Giám sát giá (PRC-001 legacy):*
- `GET /api/health` — trạng thái (collect_mode, telegram, auto_scan)
- `GET /api/catalog`, `GET /api/products`, `POST /api/products` — quản lý sản phẩm
- `GET /api/latest`, `GET /api/history/{product_id}`, `GET /api/chart`, `GET /api/alerts`
- `POST /api/run`, `POST /api/run-all` — chạy workflow
- `POST /api/autoscan/{start,stop}`, `GET /api/autoscan/status`

*Price Intelligence (PI):*
- `GET /api/price-intelligence/{catalog,overview,workspace,status}`
- `POST /api/price-intelligence/seed` — seed dữ liệu bất đồng bộ
- `GET /api/prices/{trend,index-trend,index,positioning,channel-comparison,regional,promotions,events,alerts}`
- `GET /api/prices/sku/{sku_id}`
- `POST /api/prices/{reset,collect}`
- `POST /api/ai/price-analysis` — AI Analyst (event_id hoặc question)

**Lưu ý phân kỳ với đặc tả:** `04_API_Contract.md` định nghĩa base path `/api/v1` và response envelope `{success, data, meta}`, nhưng **code thực tế dùng `/api` (không v1) và trả dict thẳng, không envelope**. `[VERIFIED]` — chênh lệch giữa `04_API_Contract.md` và `extensions/api.py`.

**Tài liệu API cũ:** `docs/API.md` tuyên bố "Không có HTTP API" — **lỗi thời**, viết trước khi lớp `extensions/` tồn tại. `[VERIFIED]` — tài liệu mô tả trạng thái kernel gốc, không phản ánh hiện tại.

---

## 8. Cơ sở dữ liệu & persistence

**SQLite** qua `sqlite3` stdlib (không ORM/driver bên ngoài). Hai DB độc lập: `[VERIFIED]`

| DB | Path (env) | Schema | Ghi bởi | Đọc bởi |
|---|---|---|---|---|
| Lịch sử giá giám sát | `HMIP_DB_PATH` (mặc định `hmip.db`) | `products`, `price_points` (+ cột `province`) | `extensions/db.py` | API giám sát |
| Price Intelligence | `HMIP_PI_DB_PATH` (mặc định `hmip_pi.db`) | `pi_brands, pi_categories, pi_products, pi_variants, pi_skus, pi_listings, pi_sellers, pi_channels, pi_regions, pi_observations, pi_promotions, pi_price_events, pi_alerts, ...` | `extensions/pi/pi_store.py` | PI analytics/events/service |

- WAL mode cho PI DB (`PRAGMA journal_mode = WAL`). Foreign keys ON. `[VERIFIED]` — `pi_store.py`.
- Migration an toàn: `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN` có bắt lỗi `OperationalError`. `[VERIFIED]` — `db.py`, `pi_store.py`.

**Persistence khác (filesystem):** `[VERIFIED]`
- Bootstrap report: `reports/bootstrap_<execution_id>.json`
- Lineage (audit trail): `knowledge/dynamic/lineage/lineage.jsonl` (JSONL append-only, mỗi record kèm SHA256 integrity hash)
- Readiness marker: `$HMIP_READY_FILE` (mặc định `<tmp>/hmip_ready`)
- Master data (read-only): `knowledge/master/{brands,products,skus}.json`

**Tài liệu cũ:** `docs/DATABASE.md` tuyên bố "Dự án KHÔNG có database" — **lỗi thời**, viết trước khi có SQLite. `[VERIFIED]`.

---

## 9. Xác thực & phân quyền

**Cơ chế:** Bearer token (đơn giản) qua FastAPI middleware toàn cục. `[VERIFIED]` — `extensions/auth.py`.

- Multi-token: đọc `HMIP_API_TOKENS` (JSON array) hoặc fallback `HMIP_API_TOKEN` (chuỗi đơn). Lookup O(1) qua set.
- Token định nghĩa qua env (không lưu DB — vì Render free ephemeral FS).
- **Dev mode:** nếu không set token → auth tự tắt, truy cập tự do.
- Route exempt (không cần token): `/api/health`, `/docs`, `/openapi.json`, `/redoc`, `/static`, `/`, `/pi`, `/workspace`.
- **Rủi ro đã ghi nhận (xem mục 20):** dashboard `/` đang exempt → ai cũng xem được dashboard shell.

**Phân quyền:** **Không tồn tại** — chỉ có hợp lệ/không hợp lệ token, không có role/permission/RBAC. `[VERIFIED]`.

**Session/JWT/OAuth:** **Không tồn tại**. `[VERIFIED]`.

**Lưu ý bảo mật đặc tả:** `docs/SECURITY.md` tuyên bố "Authentication: Không tồn tại" — **lỗi thời** (viết cho kernel gốc trước khi có lớp web + auth). `[VERIFIED]`.

---

## 10. Tích hợp bên ngoài

`[VERIFIED]` — đọc mã nguồn trực tiếp.

| Tích hợp | Cơ chế | Cấu hình env | Trạng thái |
|---|---|---|---|
| **Tiki API (công khai)** | HTTP GET `tiki.vn/api/v2/products`, cần guest token từ cookie | — (free, không key) | Hoạt động (adapter riêng, không trong chain smart) |
| **Firecrawl Extract API** | HTTP POST `api.firecrawl.dev/v1/scrape`, Bearer key | `FIRECRAWL_API_KEY` | Nguồn giá thật (tier 1 trong chain smart); cạn credit → 402 |
| **ScraperAPI** | HTTP GET `api.scraperapi.com?api_key&url&render=true&country_code=vn` | `SCRAPERAPI_KEY` | Render JS, tier 2 trong chain smart — MỚI |
| **ZenRows** | HTTP GET `api.zenrows.com/v1/?apikey&url&js_render=true` | `ZENROWS_KEY` | Render JS, tier 3 trong chain smart — MỚI |
| **Jina Reader** | `r.jina.ai/<url>` → markdown, regex parse giá + filter hotline garbage | — (free) | Fallback cuối (tier 4 trong chain smart) |
| **Crawl4AI** | Headless browser render JS | `CRAWL4AI_ENABLED`, cần chromium | Tier 5 (mặc định tắt) |
| **Telegram Bot API** (PRC-001) | POST `api.telegram.org/bot{token}/sendMessage` | `HMIP_TELEGRAM_BOT_TOKEN`, `HMIP_TELEGRAM_CHAT_ID` | Thiếu → console-log fallback |
| **Telegram** (PI) | Tương tự | `TELEGRAM_HMIP_MARKET_BOT`, `TELEGRAM_CHAT_ID` | Thiếu → skip gracefully |
| **Discord Bot API** | POST `discord.com/api/v10/channels/{id}/messages` | `DISCORD_BOT_TOKEN`, `DISCORD_HOME_CHANNEL` | Thiếu → skip gracefully |
| **OpenRouter LLM** (AI Analyst) | POST `openrouter.ai/api/v1/chat/completions` | `OPENROUTER_API_KEY`, `HMIP_PI_AI_MODEL` (mặc định `openai/gpt-4o-mini`) | Thiếu key → rule-based fallback (không bịa số) |
| **Apify** | `@niceprice/tiki-detail` actor (tuỳ chọn) | `APIFY_API_KEY`, `APIFY_ACTOR_TIKI` | Tuỳ chọn, chưa tích hợp mặc định |
| **HTTP giá nội bộ** (tuỳ chọn) | `HttpCollectAdapter` GET `{base}/{pid}` | `HMIP_PRICE_API_BASE`, `HMIP_PRICE_API_KEY`, `HMIP_PRICE_FIELD_*` | Tuỳ biến khi nối nguồn riêng |

**Thu thập giá thật 4 tầng (chain smart — fallback có thứ tự):** Firecrawl → ScraperAPI → ZenRows → Jina (→ Crawl4AI tier 5 nếu bật). Mỗi tier thử cho toàn bộ sản phẩm; nếu thu được ≥1 giá (hoặc giá không đổi = skip) → dừng, không xuống tier sau. `[VERIFIED]` — `extensions/pi/persistent_collector.py:collect_smart`, `extensions/pi/collectors.py:collect_realtime_smart`.

**Lọc giá rác + brand matching:** `extensions/pi/price_extract.py:extract_product_price` — lọc token hotline ("1000 đ/phút"), chỉ nhận giá 5k-2tr; khi truyền `brand` (tên sản phẩm) ưu tiên giá có brand keyword gần (tránh median của sản phẩm khác trên trang search). `[VERIFIED]`.

**One-time seed + incremental:** `extensions/pi/persistent_collector.py` — `has_real_prices()` kiểm tra marker `real_price_seeded=true` trong `pi_skus.metadata`; `store_price_point_if_changed()` chỉ ghi observation khi giá mới (trong noise threshold) → tránh re-scrape ghi đè; `collect_smart()` seed 1 lần rồi incremental. `[VERIFIED]`.

**Tài liệu cũ:** `docs/INTEGRATIONS.md` tuyên bố "Không có external integration" — **lỗi thời**.

---

## 11. Tác vụ chạy ngầm & worker

**APScheduler** (`BackgroundScheduler` trong web app, `BlockingScheduler` trong scheduler độc lập). `[VERIFIED]` — `extensions/api.py`, `extensions/scheduler.py`.

| Job | Trigger | Lịch | Mục đích |
|---|---|---|---|
| `hmip_auto_scan` | IntervalTrigger | `HMIP_SCAN_INTERVAL_MIN` (mặc định 30 phút) | Quét toàn bộ catalog, ghi SQLite, đẩy Telegram nếu decision≠IGNORE |
| `hmip_pi_collect` | IntervalTrigger | `HMIP_PI_COLLECT_MIN` (mặc định 30 phút) | Thu thập giá thật PI (Firecrawl→Tiki), detect events |

- Auto-scan bật khi `HMIP_AUTOSCAN=on`. Mặc định `off` trong `start.sh` nhưng `on` trong `docker-compose.yml`/`render.yaml`.
- `max_instances=1, coalesce=True` — tránh chồng chéo.
- Seed PI chạy **bất đồng bộ** (background thread) để không block startup/Render timeout. `[VERIFIED]` — `extensions/pi/service.py:seed_async`.

**Không có message queue / Celery / worker process tách rời.** Tất cả chạy trong cùng process web. `[VERIFIED]`.

---

## 12. Cấu hình & biến môi trường

**Nguồn cấu hình:** `config/*.yaml` (runtime, logging, deployment) do `ConfigLoader` nạp; mở rộng `${VAR:-default}`; freeze thành `FrozenConfig` bất biến (SHA256 fingerprint). `[VERIFIED]` — `core/config.py`.

**Biến môi trường chính:** `[VERIFIED]` — `.env.example`, `extensions/api.py`, `extensions/db.py`, `extensions/pi/`, `render.yaml`.

| Biến | Mặc định | Ý nghĩa | Đọc bởi code? |
|---|---|---|---|
| `HMIP_ENV` | development | Tên môi trường | Có (config) |
| `HMIP_DB_PATH` | `hmip.db` | DB lịch sử giá | Có |
| `HMIP_PI_DB_PATH` | `hmip_pi.db` | DB Price Intelligence | Có |
| `HMIP_COLLECT_MODE` | demo | demo/http | Có |
| `HMIP_AUTOSCAN` | off | Bật quét tự động | Có |
| `HMIP_SCAN_INTERVAL_MIN` | 30 | Chu kỳ quét (phút) | Có |
| `HMIP_PI_COLLECT_MIN` | 30 | Chu kỳ quét PI (phút) | Có |
| `HMIP_PI_AUTOSEED` | on | Auto-seed PI khi rỗng | Có |
| `HMIP_API_TOKEN` / `HMIP_API_TOKENS` | — | Bearer token auth | Có |
| `HMIP_PRICE_API_BASE`/`_KEY`/`_FIELD_*` | — | Nguồn giá http | Có |
| `HMIP_BASE_PRICE_<ID>` | — | Ghi đè giá tham chiếu | Có |
| `HMIP_TELEGRAM_BOT_TOKEN`/`_CHAT_ID` | — | Telegram (PRC-001) | Có |
| `FIRECRAWL_API_KEY` | — | Firecrawl (tier 1) | Có |
| `SCRAPERAPI_KEY` | — | ScraperAPI render JS (tier 2) | Có — MỚI |
| `ZENROWS_KEY` | — | ZenRows render JS (tier 3) | Có — MỚI |
| `OPENROUTER_API_KEY` | — | LLM AI Analyst | Có |
| `DISCORD_BOT_TOKEN`/`_HOME_CHANNEL` | — | Discord alert PI | Có |
| `HMIP_IN_DOCKER` | — | Bind 0.0.0.0 | Có (start.sh) |
| `HMIP_RUNTIME_VERSION`/`_KERNEL_VERSION` | placeholder | Phiên bản runtime | Có (models.py) |
| `HMIP_REPORT_DIR` | `reports/` | Thư mục report | Có |
| `HMIP_CONFIG_PATH` | `config/` | Thư mục config | Có |
| `HMIP_READY_FILE` | `<tmp>` | Marker readiness | Có |
| `HMIP_SECRET_PROVIDER` | — | Secret provider | **Không** (stub pass-through) |
| `HMIP_DATA_DIR` | — | Thư mục data pipeline | **Không** (chưa có pipeline) |

`.env.example` ghi rõ mỗi biến "đã nối vào code hay chỉ mới khai báo" — trung thực. `[VERIFIED]`.

---

## 13. Docker/container

**Dockerfile** (`python:3.13-slim`): `[VERIFIED]`
- Cài deps editable (`pip install -e ".[dev]"`) + fastapi/uvicorn/apscheduler/httpx/requests/crawl4ai.
- `VOLUME ["/app/data"]`, `EXPOSE 8000`.
- `CMD ["./start.sh", "--port", "8000"]`.
- **Lưu ý phân kỳ:** Dockerfile dùng `python:3.13-slim` nhưng `pyproject.toml`/`config/deployment.yaml`/`SPRINT_6` ghi `python:3.12-slim`. Dockerfile gốc (Sprint 6) là 3.12-slim; phiên bản hiện tại đã nâng lên 3.13.

**docker-compose.yml (root):** service `hmip`, port 8000:8000, volume `hmip_data:/app/data`, env HMIP_*, restart unless-stopped. Token mặc định `changeme-in-production` (cảnh báo phải đổi). `[VERIFIED]`.

**deployment/docker-compose.yml:** service `hmip-bootstrap`, **không expose port** (mô tả mô hình run-to-completion CLI), healthcheck `python -m platform_.health`, volume reports/data/knowledge-dynamic. `[VERIFIED]`.

**render.yaml:** Render Blueprint, web service runtime docker, healthCheckPath `/api/health`, auto-generate `HMIP_API_TOKEN`. Env `FIRECRAWL_API_KEY`, `SCRAPERAPI_KEY`, `ZENROWS_KEY` set `sync: false` (điền qua Render Dashboard, không commit). `[VERIFIED]`.

**deployment/kubernetes/:** `[VERIFIED]`
- `job.yaml` — Kubernetes **Job** (batch, backoffLimit 2, restartPolicy Never) vì "không có HTTP server" — entrypoint `python -m platform_.bootstrap`.
- `configmap.yaml` — chỉ chứa `HMIP_ENV`/`HMIP_LOG_LEVEL` (non-secret).

**Lưu ý kiến trúc:** Tài liệu `job.yaml` mô tả mô hình CLI (không port), nhưng `Dockerfile`/`docker-compose.yml`/`render.yaml` chạy web server có port. Đây là **hai mô hình triển khai tồn tại song song**. `[INFERRED]`.

---

## 14. Quy trình CI/CD

**Không tìm thấy thư mục `.github/workflows/` hoặc bất kỳ file CI/CD nào** trong repo. `[VERIFIED]` — `find .github` không tồn tại, `git ls-files` không có file workflow GitHub Actions.

- `pyproject.toml` có cổng coverage `--cov-fail-under=80` (chạy qua pytest) — đây là duy nhất gần với CI gate, nhưng **không có workflow tự động chạy**.
- Đặc tả `01_System_Specification.md` mục 2.5 liệt kê "CI/CD" thuộc Operations Layer nhưng chưa hiện thực.
- `09_Deployment_Guide.md` mô tả quy trình deploy thủ công (build image → push registry → Render/Fly/Railway).
- `deployment/RELEASE_CHECKLIST.md` có quy trình release 6 bước (thủ công).

`[UNKNOWN]` — không có bằng chứng về pipeline CI/CD tự động. `[VERIFIED]` rằng nó vắng mặt.

---

## 15. Chiến lược kiểm thử (testing)

**Pytest**, **415 pass / 1 skip**, coverage **94.28%** (gate ≥80%). `[VERIFIED]` — chạy trực tiếp (Python 3.13, 2026-08-17). Test PI mở rộng qua các PR: `price_extract` (filter hotline + brand matching + pack-aware), `persistent_collector` (marker + incremental + notify + **so sánh per-lon PR #13**), `test_pack_normalize` (clamp pack PR #13), `test_notify_rate_limit_sys2` (guard "tham chiếu" absent), `test_pi` (+5 test PR #12: brand Unknown/promo/channels/migrate_brand_ids).

**Phân loại:** `[VERIFIED]` — `tests/`, `extensions/tests/`, `domains/beer/pricing/tests/`
- `tests/unit/` — core (bootstrap, config, registry, planner, executor, workflow, event_bus, lineage, models, ontology, health, readiness, platform_bootstrap, context)
- `tests/integration/` — workflow execution flow
- `tests/workflow/` — PRC-001 end-to-end, compensation, regression
- `tests/chaos/` — network timeout, deadlock, disk full, storage failure, dependency unavailable
- `tests/prompt/` — golden dataset (decision engine, extract price)
- `extensions/tests/` — web layer (auth, api, chart, add_product, http_adapter, automation, pi)
- `domains/beer/pricing/tests/` — domain skills (decision_engine, enrich, models, skills)

**Cổng coverage:** ≥80% (unit), ≥90% (workflow critical, review thủ công). `[VERIFIED]` — `pyproject.toml`.

**Trạng thái test hiện tại:** **415 pass / 1 skip**, coverage 94.28% (gate ≥80%). `[VERIFIED]` — chạy `python -m pytest` trực tiếp (2026-08-17, sau PR #12 + #13). Lịch sử: 11 test từng fail do master data `knowledge/master/*.json` đổi sang tên tiếng Việt ("Bia Sài Gòn") nhưng test assert tiếng Anh cũ — **đã sửa (2026-08-16)** bằng đồng bộ mock adapter + assertion + golden dataset. Không còn test fail.

---

## 16. Logging & observability

**Logging có cấu trúc:** structlog → JSON, ra stdout. `[VERIFIED]` — `core/observability.py`.
- Trường tối thiểu theo spec: timestamp, execution_id, trace_id, component, event_type, status, duration_ms, error_code.
- Idempotent (an toàn gọi nhiều lần).
- API layer dùng stdlib `logging` riêng (`logging.getLogger("hmip.api")`), **không** qua structlog — tách biệt với core.

**Lineage (audit trail):** `[VERIFIED]` — `core/lineage.py`
- `PersistentLineageTracer` ghi `lineage.jsonl` (append-only), mỗi record kèm SHA256 integrity hash.
- Mặc định `WorkflowEngine` dùng `InMemoryLineageTracer`; `run_workflow.py` inject `PersistentLineageTracer` + memory dual tracer.

**Health/Readiness:** CLI exit-code (không HTTP trong kernel gốc), nhưng API có `GET /api/health` (web layer). `[VERIFIED]`.

**Metrics/Prometheus/Distributed tracing:** **Không tồn tại**. `[VERIFIED]`.

**Rủi ro R-01 (logging):** `config/logging.yaml` khai báo `redact_fields` (password, token, secret, api_key) nhưng **không có logic redact nào** trong `observability.py` — cảm giác an toàn giả. `[VERIFIED]` — `docs/SECURITY.md` R-01.

---

## 17. Thư viện/thành phần phụ thuộc chính

`[VERIFIED]` — `pyproject.toml`, `requirements.txt`, `Dockerfile`.

| Thư viện | Vai trò | Nguồn khai báo |
|---|---|---|
| pyyaml | Parse config/workflow YAML | pyproject + requirements |
| structlog | Structured JSON logging | pyproject + requirements |
| jsonschema | Validate ontology + price schema | pyproject + requirements |
| fastapi | Web framework | requirements + Dockerfile |
| uvicorn | ASGI server | requirements + Dockerfile |
| pydantic | API model validation | requirements |
| apscheduler | Background scheduling | requirements + Dockerfile |
| httpx | HTTP client (PRC-001 http adapter, Telegram) | requirements + Dockerfile |
| requests | HTTP client (PI collectors) | Dockerfile |
| crawl4ai | Headless browser crawling (tier 4) | Dockerfile (chỉ container) |
| pytest / pytest-cov | Testing | pyproject [dev] |
| ruff | Lint | pyproject [dev] |
| mypy | Type check (strict) | pyproject [dev] |

**Quản lý lock:** `uv.lock` (118KB) dùng cho local dev với `uv`. `[VERIFIED]`.

---

## 18. Rủi ro tiềm ẩn về kiến trúc

1. **Hai mô hình runtime mâu thuẫn:** Kernel gốc là run-to-completion CLI (`platform_/bootstrap`), nhưng lớp web `extensions/api` biến nó thành long-running server. `job.yaml` (K8s Job, không port) và `docker-compose.yml` (port 8000) triển khai hai mô hình khác nhau. `[VERIFIED]`.
2. **`docs/` lỗi thời nghiêm trọng:** `docs/DATABASE.md`, `docs/API.md`, `docs/INTEGRATIONS.md`, `docs/SECURITY.md` mô tả trạng thái kernel gốc (Sprint 1-6) và **không phản ánh** lớp `extensions/` (web API, SQLite, auth, tích hợp ngoài). Đọc tài liệu này sẽ hiểu sai hệ thống. `[VERIFIED]`.
3. **Compensation rỗng:** Cả 7 rollback của PRC-001 đều là no-op — cơ chế thật, nội dung rỗng. Khi có side effect thật (notification, DB write) thì rollback sẽ không hoàn tác gì. `[VERIFIED]` — `registrar.py` docstring.
4. **`cancel()` vô hiệu:** `WorkflowEngine.cancel()` vô hiệu thực tế vì `execute()` đồng bộ, tự sinh `execution_id`, caller không biết id trước khi hàm trả. `[VERIFIED]` — `workflow_engine.py` docstring.
5. **Readiness marker không xoá:** `clear_ready()` tồn tại nhưng không gọi ở đâu → marker tồn tại vĩnh viễn. Với `emptyDir` (K8s) thì không phát sinh, nhưng với volume bền vững thì readiness sẽ luôn READY. `[VERIFIED]` — `docs/SECURITY.md` R-03.
6. **Config không validate schema:** `ConfigLoader.validate()` chỉ kiểm tra kiểu dict. `[VERIFIED]`.
7. **Retry policy không diễn giải đúng:** `RetryPolicy.strategy` lưu nhưng không diễn giải — backoff luôn tuyến tính. `[VERIFIED]` — `docs/ARCHITECTURE.md` mục 10.
8. **Single-process, không scale:** Tất cả scheduler + web + worker trong 1 process. Không thể scale ngang (replica) mà không chuyển SQLite sang Postgres. `[INFERRED]` — `DEPLOY.md` mục "Lưu ý bảo mật".
9. **Render free ephemeral FS:** data reset mỗi restart → auto-seed lại (mất lịch sử thật). `[VERIFIED]` — `render.yaml` comment.

---

## 19. Nợ kỹ thuật (technical debt)

1. **~~11 test đang fail~~ (ĐÃ SỬA 2026-08-16):** mismatch master data tiếng Việt vs assert tiếng Anh cũ. Đã đồng bộ mock collect adapter + assertion + golden dataset. Suite hiện **415 pass / 1 skip** (sau PR #12 + #13). `[VERIFIED]`.
2. **API không tuân contract:** `04_API_Contract.md` (base `/api/v1`, response envelope) vs thực tế (`/api`, dict thẳng). `[VERIFIED]`.
3. **Orphaned `platform/` folder:** ADR-010 ghi rõ folder `platform/` cũ vẫn còn trên disk (tools không xoá được), phải xoá thủ công trước khi chạy test. `[VERIFIED]` — `SPRINT_6_STATUS.md`, `ADR_010`. *(Lưu ý: trong clone này, thư mục `platform/` không còn — chỉ còn `platform_/`.)*
4. **Secret resolution stub:** `_resolve_secrets()` là pass-through. `[VERIFIED]` — `core/config.py`.
5. **`HMIP_DATA_DIR`/`HMIP_SECRET_PROVIDER` khai báo nhưng không đọc.** `[VERIFIED]` — `.env.example`.
6. **`_MOCK_SOURCE_DATA` chỉ 1 bản ghi** (kernel gốc) — workflow kernel chỉ chạy được với P123+shopee; lớp `extensions/` đã giải quyết bằng adapter riêng. `[VERIFIED]`.
7. **Prompt file không được code đọc:** `domains/beer/pricing/prompts/extract_price.md` tồn tại nhưng `extract_price.py` dùng parser tất định. `[VERIFIED]` — `docs/INTEGRATIONS.md` mục 2.
8. **`shared/types.py` 0% coverage** (file không dùng). `[VERIFIED]` — pytest coverage report.
9. **Inconsistent env var naming:** Telegram PRC-001 dùng `HMIP_TELEGRAM_*`, PI dùng `TELEGRAM_HMIP_MARKET_BOT`/`TELEGRAM_CHAT_ID` (không prefix `HMIP_`). `[VERIFIED]`.
10. **`.dockerignore` loại `*.md` và `docs/`** → tài liệu không có trong image (có chủ đích), nhưng cũng loại luôn cả tài liệu vận hành. `[VERIFIED]`.
11. **`mark_ready` UnboundLocalError (ĐÃ SỬA):** `extensions/pi/service.py:mark_ready` gán `_seed_state` trong hàm mà không khai `global` → khi lifespan gọi `mark_ready` (nhánh marker) lỗi "cannot access local variable". **Đã sửa** bằng `global _seed_state`. `[VERIFIED]`.
12. **`pi_skus` thiếu cột `metadata` (ĐÃ SỬA):** schema cũ không có cột lưu marker `real_price_seeded`. **Đã thêm** cột `metadata` vào CREATE TABLE + migration `ALTER TABLE ADD COLUMN` (idempotent qua PRAGMA). `[VERIFIED]` — `pi_store.py:init_pi_db`.

---

## 20. Khu vực nhạy cảm về bảo mật

`[VERIFIED]` — đọc trực tiếp mã nguồn/tài liệu.

| Khu vực | Trạng thái | Chi tiết |
|---|---|---|
| **API key hardcode trong repo** | 🔴 **RỦI RO CAO** | `render.yaml` dòng 39 (trước khi sửa) chứa `FIRECRAWL_API_KEY` giá trị thật hardcoded. Secret đã bị lộ vào commit `32335cb`. **Đã xử lý:** đổi sang `sync: false` (Render Dashboard điền, không commit). **Vẫn cần thu hồi key cũ** vì nó đã ở trong git history. Xem phần xử lý bên dưới. |
| **Token mặc định yếu** | ⚠️ RỦI RO | `docker-compose.yml` `HMIP_API_TOKEN: changeme-in-production` — cảnh báo phải đổi, nhưng ai quên sẽ mở internet với token mặc định. |
| **Auth có thể tắt** | ⚠️ Thiết kế | Không set `HMIP_API_TOKEN` → auth tắt hoàn toàn (dev mode). Deploy quên set token = không bảo vệ. |
| **Dashboard exempt khỏi auth** | ⚠️ RỦI RO | `/`, `/pi`, `/workspace` (dashboard shell HTML) nằm trong `_EXEMPT_EXACT` → không cần token. HTML tải được (dù fetch API cần token). `DEPLOY.md` khuyến nghị đóng `/docs` ở production. |
| **`/docs`, `/openapi.json` exempt** | ⚠️ RỦI RO | Schema API lộ ra khi deploy public dù đã bật auth. `DEPLOY.md` ghi rõ cách đóng. |
| **Lineage ghi nguyên input/output** | ⚠️ RỦI RO R-02 | `PersistentLineageTracer` serialize toàn bộ payload không lọc. Hiện tại chỉ là giá công khai, nhưng nếu có PII/credential sẽ nằm nguyên trong `lineage.jsonl`. |
| **`redact_fields` giả** | ⚠️ R-01 | `logging.yaml` khai báo redact nhưng không có logic — cảm giác an toàn giả. |
| **SQLite không mã hoá** | ℹ️ | DB file chứa dữ liệu giá, không mã hoá at-rest. Gắn volume → truy cập file = truy cập data. |
| **TLS/HTTPS** | ℹ️ | App serve HTTP; HTTPS do platform (Render) chấm dứt. Không kiểm soát được trong app. |
| **Dependency scan** | `[UNKNOWN]` | Chưa chạy `pip-audit`/`safety` — không có CI. |
| **No CSRF/CORS protection** | ℹ️ | API dùng Bearer token (không cookie) nên CSRF ít liên quan; CORS không cấu hình. |
| **`.hermes/.env` load từ home dir** | ⚠️ | `extensions/pi/notifier.py:_maybe_load_env` đọc `~/.hermes/.env` để nạp env thiếu — tiềm ẩn đọc file ngoài workspace. |

**Cơ chế bảo vệ đã có (đáng khen):** `[VERIFIED]` — `docs/SECURITY.md`
- Không bake secret vào image (`Dockerfile`).
- ConfigMap không chứa secret.
- Không `eval`/`exec`/`shell=True`.
- `yaml.safe_load` ở mọi nơi.
- JSON Schema validation + ontology referential integrity.
- Config/Registry bất biến sau freeze.

---

## Phụ lục: Trạng thái tài liệu `docs/` (cảnh báo)

Các file `docs/*.md` (ARCHITECTURE, SECURITY, DATABASE, API, INTEGRATIONS, ...) được tạo ở **Phase 2-3** và phản ánh **kernel gốc** (chỉ `core/`, `domains/`, `knowledge/`, `platform_/`), **trước khi** lớp `extensions/` (web API, SQLite, auth, collector thật, PI module) được thêm vào. Đặc biệt:
- `docs/DATABASE.md` — "KHÔNG có database" → **SAI** (có SQLite).
- `docs/API.md` — "Không có HTTP API" → **SAI** (có FastAPI).
- `docs/INTEGRATIONS.md` — "Không có external integration" → **SAI** (Tiki/Firecrawl/Jina/Telegram/Discord/OpenRouter).
- `docs/SECURITY.md` — "Authentication: Không tồn tại" → **SAI** (có Bearer token).
- `docs/ARCHITECTURE.md` — chính xác về kernel nhưng không đề cập lớp web.

Tài liệu này (`CODEBASE_OVERVIEW.md`) phản ánh **trạng thái hiện tại** đầy đủ. Khi cần tra kernel, dùng `docs/ARCHITECTURE.md` (vẫn chính xác cho phần core); khi cần tra web/PI, dùng tài liệu này và mã nguồn `extensions/`.

`[VERIFIED]` — so sánh trực tiếp `docs/*` với mã nguồn hiện tại.
