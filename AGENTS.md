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

# Chạy test (hiện 415 pass / 1 skip; coverage 94.28%)
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
  - `api.py` — FastAPI (tất cả endpoint `/api/*`), lifespan seed PI + **PR #12: gọi `migrate_brand_ids()`** (backfill brand_id observation, xoá Unknown)
  - `db.py` — SQLite lịch sử giá (path: `HMIP_DB_PATH`)
  - `pi/` — Price Intelligence (DB riêng `HMIP_PI_DB_PATH`, schema đầy đủ)
    - `collectors.py` — `collect_realtime_smart` (delegate sang `collect_smart` 4-tier chain); `TikiCollector` (API JSON), `ShopeeCollector`/`LazadaCollector` delegate sang ScraperAPI/ZenRows/Jina (collect_html, render JS) — không còn stub NotImplementedError
    - `channels.py` — **channel registry** (TIKI/SHOPEE/LAZADA + TIKTOK/GRABMART từ PR #12): search_url + api_url + strategy; `configured_channels()` đọc `HMIP_CHANNELS`
    - `persistent_collector.py` — `has_real_prices` (marker), `store_price_point_if_changed` (incremental), `collect_smart` (4-tier chain, multi-channel)
    - `price_extract.py` — `extract_product_price(brand=)` dùng chung: filter hotline garbage + brand matching
    - `firecrawl_collector.py` (tier 1), `scraperapi_collector.py` (tier 2), `zenrows_collector.py` (tier 3), `jina_collector.py` (tier 4)
    - `service.py` — orchestration; `mark_ready` đã sửa `global _seed_state`
  - `report_engine.py` — **Daily Intelligence Report** ("Context Once — Delta Every Day"): build 7-section (EXEC SUMMARY → NEW → CHANGED → WATCHLIST → ACTIONS → SIGNALS → HISTORY), render markdown Telegram/Discord, send qua `notifiers.send_text`. Phân loại theo events của NGÀY REPORT (không `last_updated` hiện tại) → backfill ngày quá khứ đúng. Test: `extensions/tests/test_pi_daily_report.py` (10 test); render smoke TestClient (PR #20).
    - **Fallback `market_snapshot` (26/08):** khi `changed_today` rỗng (PI DB không có event), payload nạp thêm snapshot giá thật từ `knowledge/master/prices_real.json` (Job 1 daily scan → reconcile) + `_sync_meta.json` của beer_scan → báo cáo KHÔNG BAO GIỜ TRẮNG. Mỗi item gồm giá thùng/lẻ, dải min–max qua kênh, số kênh, ngày scan + ngày reconcile; render vào section 2 (email HTML + markdown). Khi có delta thật, `market_snapshot=None` → format delta nguyên thủy.
  - `pi_store.py` — thêm `pi_topics` (Intelligence Event có vòng đời: first_seen/last_updated/status/baseline/current/total delta/last_event id). `rebuild_topics()` idempotent (delete+insert, giữ `last_reported_at`); gọi cuối `detect_events()`.
    - `pi_store.py` — đã thêm cột `metadata` cho `pi_skus` (marker); **PR #12: `migrate_brand_ids()`** backfill `brand_id` observation từ `pi_products.brand_id`, xoá brand rỗng/Unknown (idempotent, wire vào `api.py` lifespan startup)
    - `analytics.py` — **PR #12:** JOIN `pi_brands` qua `pi_products.brand_id` (không qua `pi_observations.brand_id`) cho `positioning_matrix()`/`catalog()`/`competitor_comparison()` → Competitor Comparison + Price Index (by Brand) không còn "Unknown"; **+`promotion_by_brand` + `promotion_timeline`** (chart Promotion Intelligence)
  - `run_workflow.py` — NỐI kernel vào runtime thật (fix F-01)
  - `web/index.html` + `web/pi.html` — i18n 3 ngôn ngữ (vi/en/zh) trong dict `T` / `I18N`; login overlay có bộ chọn riêng `#loginLangSeg` (header seg bị overlay che). Khi thêm chuỗi UI mới: thêm key vào CẢ 3 dict, đánh dấu `data-i18n` trong markup; chuỗi set bằng JS (hint/lỗi) phải qua `t(key)` — đừng hardcode. Modal Clerk (Sign in/Sign up/Quên mật khẩu) dịch qua `CLERK_LOCALES` (object trong cùng 2 file, key theo LocalizationResource của Clerk — ví dụ `signIn.start.title`); **Clerk chỉ nhận `localization` lúc `Clerk.load()`** → `setLang()` khi đang ở màn login phải `location.reload()` để modal theo ngôn ngữ mới. Test modal local được bằng `CLERK_PUBLISHABLE_KEY` (public key, lấy từ `/api/auth/clerk-config`)
  - `collect_adapters.py` — adapter giá (demo/http/Tiki 3 tầng — legacy, riêng PI dùng chain smart)
  - `auth.py` — Bearer token middleware
- **`domains/beer/pricing/`** — vertical slice PRC-001 (7 task: collect→extract→validate→enrich→compare→decide→alert)
- **`knowledge/master/*.json`** — master data (Brand/Product/SKU). Đã chuyển sang tên tiếng Việt.

## Thu thập giá thật (PI) — chain 4 tầng

Thứ tự fallback: **Firecrawl → ScraperAPI → ZenRows → Jina** (→ Crawl4AI tier 5 nếu `CRAWL4AI_ENABLED`).

### Multi-channel (Tiki + Shopee + Lazada)

- **Channel registry:** `extensions/pi/channels.py` định nghĩa TIKI/SHOPEE/LAZADA + **TIKTOK/GRABMART (PR #12)** — mỗi kênh có `search_url(query)` (URL trang search) + `api_url(query)` (API JSON nếu có). Tiki = strategy "api" (gọi `/api/v2/products` parse JSON chính xác); Shopee/Lazada/TikTok/GrabMart = strategy "html" (scrape trang search + `extract_product_price` pack-aware, vì không có public API dễ gọi).
- **Bật kênh qua env:** `HMIP_CHANNELS=tiki,shopee,lazada,tiktok,grabmart` (**mặc định 5 kênh từ PR #12** — trước PR #12 chỉ `tiki`). Mỗi kênh lưu observation riêng (`channel_id` khác) → so sánh giá cross-channel trong UI/analytics. Seed demo `_CHANNEL_FACTOR` mở rộng 18 kênh (factor thực tế: Shopee 0.90 rẻ nhất, Circle K 1.10 đắt nhất).
- **Tier collectors đa kênh:** `FirecrawlCollector/ZenRowsCollector/JinaCollector.collect(channel=...)` nhận ChannelConfig, dùng `channel.search_url(query)` thay vì hardcode Tiki. `ScraperAPICollector.collect(channel=...)` dispatch: Tiki → API JSON (`_api_search`), Shopee/Lazada → HTML search (`collect_html`).
- **`_collect_via_chain` quét multi-channel:** vòng ngoài = kênh, vòng trong = sản phẩm. Tier thành công nếu TỔNG collected/skipped qua các kênh > 0 (không yêu cầu tất cả kênh đều có giá — Shopee/Lazada có thể fail do bot protection mạnh).
- **Giới hạn thực tế:** Shopee có bot protection mạnh (chống scrape) → ScraperAPI/ZenRows (render JS + proxy residential) có khả năng cao nhất cào được; Jina (không render JS) thường trả None cho SPA Shopee. Lazada (Akamai) khó hơn. Nếu một kênh fail, kênh khác vẫn ghi observation → không mất dữ liệu.

### Mismatch đơn vị thùng/lon (đã fix PR #6) — LƯU Ý QUAN TRỌNG

**Vấn đề:** `base_price` (`ref_price` trong `DEFAULT_PRODUCTS`) là giá **1 LON** (~18k-40k). Collector cào Tiki thật, item match đầu tiên cho "Peroni 330ml" thường là **THÙNG 24 lon** (~240k-635k) chứ không lon lẻ → so giá thùng vs base lon → variance 479-1818% → ESCALATE sai liên tục (nguồn spam).
**Fix (apples-to-apples với base lon):**
- `collectors._match_best`: score `(brand_match, -pack)` → **ưu tiên lon lẻ** (pack=1); thùng (pack 6/12/24) chỉ lấy khi không có lon lẻ.
- `TikiCollector.collect` + `ScraperAPICollector.collect`: parse `pack_quantity` từ **tên ITEM thật** (`best.name`), fallback tên config.
- `_TikiRealAdapter.fetch` (run_prc_001 path): trả `unit_price = eff / pack_quantity` (giá/lon) → `price_text` hiển thị + compare với base lon cùng đơn vị.
**Giới hạn:** ZenRows/Jina dùng `extract_product_price` trên HTML (không có item name) → từng parse pack từ config (lon=1). Đã fix 3 lớp (PR #7 + #8 + #9):
- **PR #7:** adapter heuristic — nếu pack==1 (config) nhưng eff>100000 (ngưỡng thùng) → chia 24 (thùng bia VN thường 24 lon). 736000/24=30667/lon.
- **PR #8:** `extract_product_price._pick_price` ưu tiên nhóm giá LON (≤50000đ) khi trang search có cả lon lẻ + thùng; nếu chỉ thùng → fallback median thùng (adapter PR #7 chia 24).
- **PR #9 (fix dứt điểm):** `extract_product_price` nay **pack-aware** — parse `pack_quantity` từ context HTML SAU giá ("thùng 24 lon", "24 chai", "x24", "lon 24"...) và chuẩn hoá giá THÙNG về giá/LON ngay tại extract. Sửa triệt để mismatch cho SP chỉ có item THÙNG trên Tiki (Bia Sư Tử Trắng, Huda — lon lẻ hết hàng): extract trả giá/lon chính xác (vd 736000/24=30667) thay vì giá thùng → không còn lệch so base lon. Window context hẹp (32 ký tự SAU giá, KHÔNG dùng window trước) để tránh bắt pack token của sản phẩm khác (bleed). Fallback median thùng chỉ khi KHÔNG parse được pack → adapter heuristic /24 (lưới an toàn cuối). Test: `test_extract_price_pack_aware_normalizes_box_to_lon`, `test_extract_price_prefers_lon_when_both_present`, `test_extract_product_price_falls_back_to_thung_when_no_lon`.
- **PR #11 (price-based pack inference):** khi context HTML KHÔNG nêu rõ pack ("thùng 24") mà chỉ có giá THÙNG, `extract_product_price` nhận thêm `base_price` (giá 1 lon từ catalog `DEFAULT_PRODUCTS.ref_price`) → suy pack từ tỷ số `box/base` snap về 6/12/24 gần nhất (`_infer_pack_from_price`, cho phép sai số ±30%). Chính xác hơn /24 cứng (PR #9 chỉ chia 24, sai khi SP là thùng 6 hoặc 12 lon → giá/lon lệch). 3 collector HTML (Jina/ZenRows/ScraperAPI) truyền `base_price` qua helper `_resolve_base_price(product_id)`; adapter `_TikiRealAdapter.fetch` cũng dùng `_infer_pack_from_price` thay /24 cứng khi pack==1 và eff>100000. Test: `test_infer_pack_from_price_snaps_to_common_packs`, `test_extract_price_base_price_inference_when_no_pack_context`, `test_extract_price_base_price_inference_thung_12`.
- **PR #13 (clamp pack ở `_parse_pack_volume`):** regex cũ `(\d+)\s*lon` bắt **mọi** số trước "lon" → "Combo 450 lon"=pack 450, "Lon 330"=pack 330 → sinh "Giá thùng (450 lon)" vô lý trong alert. Giờ `_parse_pack_volume` (collectors.py, path API Tiki) **clamp pack về {6,12,24}** (lon lẻ=1): số lạ bị reject, "thùng"→24, còn lại→1. Khớp với `price_extract._detect_pack` (đã `[2,48]`) và `_infer_pack_from_price` (đã snap {6,12,24}). Test: `test_parse_pack_volume_clamps_absurd_pack`.

### Tier chain & circuit breaker

- **Circuit breaker Firecrawl:** khi API trả 402 (hết credit), `FirecrawlCollector._credit_exhausted=True` → các SP còn lại trong run skip Firecrawl ngay (0s thay vì 60s timeout mỗi SP), xuống ScraperAPI/ZenRows/Jina. Flag reset khi nhận 200 lại (credit refresh) hoặc process restart.
- **Firecrawl credit schedule:** key `fc-abc42...` refresh credit định kỳ (kỳ tới ~14/09). Trong khi chờ, auto-scan incremental (`HMIP_PI_COLLECT_MIN=360` = 6h) dùng ScraperAPI/ZenRows/Jina. Chỉ ghi observation + notify khi giá **thay đổi** (noise threshold 1%); giá không đổi → skip (không re-seed toàn bộ).
- **Hai hệ thống notify (chạy song song, chia sẻ cross-scope cooldown để chống double-notify):**
  - **Hệ 1 (PI incremental):** `extensions/pi/notifier.py::notify_alert` — cho alert giá thay đổi từ `store_price_point_if_changed`. **PR #13 (2026-08-17, fix độ chính xác giá):** `store_price_point_if_changed` giờ **so sánh + alert trên giá/LON** (`effective_price / pack_quantity` = `norm.price_per_unit`), **KHÔNG còn so raw `effective_price`**. Trước đây so raw giữa observation có pack khác nhau (thùng 1.15M vs lon lẻ 15,333) sinh alert sai `-98.67%` giả tạo + gán nhãn giá thùng là "VND/lon". Giờ `_latest_observation` JOIN `pi_skus.pack_quantity` + lấy `unit_price` (giá/LON đã chuẩn hoá lúc insert); DB cũ thiếu `unit_price` → suy lại `effective_price/pack`. Alert mang per-lon old/new → change_pct thật (vd `-68%`). `notifier._format` hiện `Giá/LON: ...₫ → ...₫/lon (X%)` + `Giá thùng (24 lon): ...` (= per-lon × 24, thùng bia VN tiêu chuẩn, **không phụ thuộc pack item cào được** — tránh "Giá thùng (1 lon)" hay "(450 lon)" vô lý). Dòng "Giá tham chiếu (lon)" **đã xoá** khỏi message (cả Hệ 1 `pi/notifier.py` lẫn Hệ 2 `notifiers/telegram.py`+`discord.py`) theo yêu cầu user — `base_price` vẫn trong signature notify (caller vẫn truyền) nhưng không render. Anti-spam **5 lớp** (PR #11): (0) **cross-hệ cooldown** (`HMIP_NOTIFY_SKU_COOLDOWN_MIN`, default 120', key `prod:<product_name>` scope `pi-sku`) — nếu hệ 2 (scheduler) đã notify SP này gần đây → skip, tránh 2 hệ gửi 2 messages cho cùng SP; (1) **per-product cooldown** (PR #11 mới, `HMIP_NOTIFY_PRODUCT_COOLDOWN_MIN`, default 240'=4h, key `prod:<product_name>`) — gộp 90 cặp (sku,channel,region)=18 kênh×5 vùng thành 1 alert per SP; (2) min-change (`HMIP_NOTIFY_MIN_PCT`, default **8** từ PR #11 — tăng từ 5 vì giá bia dao động 5-10% là thường); (3) **per-sku cooldown** (cùng env `HMIP_NOTIFY_SKU_COOLDOWN_MIN`, default 120', key `sku:sku_id|region_id`); (4) cooldown per `(sku,channel,region)` (`HMIP_NOTIFY_COOLDOWN_MIN`, default 360'=6h; `0`=tắt). Ngoại lệ: giá đổi ≥5% so với mốc cross/per-sku → event mới → vẫn cho phép notify. State BỀN VỮNG (PR #9): ngoài cache in-memory, mốc lần gửi cuối ghi bảng `pi_notify_state` (scope "pi"/"pi-sku") qua `pi_store.set_notify_state`; restart → đọc DB → cooldown sống. Chỉ ghi nhận khi ≥1 kênh gửi thành công. **PR #11 fix bug cross-hệ key**: trước đây alert ghi `product_name=pp.product_id` ("P123") ≠ scheduler truyền tên thật ("Bia Huda") → key khác nhau → cross-hệ skip không hoạt động. Giờ resolve tên SP thật từ `DEFAULT_PRODUCTS` trong `store_price_point_if_changed`.
  - **Hệ 2 (PRC-001 scheduler):** `extensions/notifiers/notify_all` (telegram.py + discord.py) — cho alert từ `scheduler.scan_once` → `run_prc_001`. Anti-spam 4 lớp tại `extensions/notifiers/rate_limit.py::allow` (funnel chung): min-change (`HMIP_SCAN_NOTIFY_MIN_PCT`, default 10 → chỉ ESCALATE đi qua) + **cross-hệ cooldown** (PR #11: default 120' thay vì 30', đọc `prod:<name>` scope `pi-sku` — nếu hệ 1 PI collect đã notify SP gần đây → skip; giá đổi ≥5% thì cho phép) + cooldown per sản phẩm (`HMIP_SCAN_NOTIFY_COOLDOWN_MIN`, default 360'=6h; `0`=tắt; giá đổi ≥5% thì vẫn báo) + no-repeat (cùng decision+giá → skip). State bền vững: `mark_sent` ghi `pi_notify_state` (scope "scan" + cross-scope "pi-sku"). Severity trong collector (hệ 1) theo magnitude thực (CRITICAL≥10/HIGH≥5/MEDIUM≥3/LOW), không cứng CRITICAL.
- **Notify:** `notifier.py` gửi alert Telegram (`TELEGRAM_HMIP_MARKET_BOT` + `TELEGRAM_CHAT_ID`) + Discord (`DISCORD_BOT_TOKEN` + `DISCORD_HOME_CHANNEL` hoặc `DISCORD_DM_USER_ID` để DM trực tiếp tới user). Chỉ trigger khi `store_price_point_if_changed` phát hiện giá đổi.

- `collect_smart(limit, path)` trong `persistent_collector.py` thử từng tier cho toàn bộ sản phẩm.
- Tier thành công khi: thu được ≥1 observation mới (`collected>0`) HOẶC có giá không đổi (`skipped>0`, tức tier lấy được giá nhưng không cần ghi lại). Chỉ xuống tier sau khi cả hai đều 0.
- **One-time seed:** `has_real_prices()` kiểm marker `real_price_seeded=true` trong `pi_skus.metadata`. Seed 1 lần → marker đặt → không re-seed synthetic nữa.
- **Incremental:** `store_price_point_if_changed` chỉ ghi observation khi giá mới (ngoài noise threshold). Giá không đổi → skip (không ghi đè).
- **Lọc rác:** `extract_product_price(html, brand)` — loại token hotline ("1000 đ/phút"), chỉ nhận 5k-2tr; brand matching ưu tiên giá gần tên thương hiệu (tránh median sản phẩm khác).
- Env: `FIRECRAWL_API_KEY`, `SCRAPERAPI_KEY`, `ZENROWS_KEY` (Render: `sync: false`). Code đọc `SCRAPERAPI_KEY`/`ZENROWS_KEY` (không phải `_API_KEY`). Multi-channel: `HMIP_CHANNELS=tiki,shopee,lazada,tiktok,grabmart` (**mặc định 5 kênh từ PR #12**).

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
- ~~Test fail hiện tại (11): do `knowledge/master/*.json` đổi tên "Saigon Beer"→"Bia Sài Gòn" nhưng test vẫn assert tên cũ.~~ **ĐÃ SỬA (2026-08-16):** đồng bộ mock collect adapter (`collect_price.py`) + assertion trong `tests/unit/test_ontology.py`, `domains/beer/pricing/tests/test_enrich_price.py`, `domains/beer/pricing/tests/test_skills.py`, và golden dataset (`tests/prompt/golden/extract_price_golden.json`) sang "Bia Sài Gòn" khớp master data. Full suite 268 pass / 0 fail. **Cập nhật (2026-08-17, PR #12 + #13):** suite nay **415 pass / 1 skip**, coverage 94.28% — PR #12 thêm 5 test PI (brand Unknown/promo/channels) + sửa `test_migrate_brand_ids_backfill_empty` (assertion "pre" theo fix product-join); PR #13 thêm 3 test (pack clamp, so sánh per-lon, message accuracy) + guard "tham chiếu" absent trong `test_notify_rate_limit_sys2.py`.
- Test PI (`extensions/tests/test_pi.py`) cần có thể seed DB — chạy trong tmp.

## Cấu hình & env

- Config: `config/{runtime,logging,deployment}.yaml`, mở rộng `${VAR:-default}`, freeze bất biến.
- DB paths: `HMIP_DB_PATH` (mặc định `hmip.db`), `HMIP_PI_DB_PATH` (mặc định `hmip_pi.db`).
- Auth: `HMIP_API_TOKEN` (đơn) hoặc `HMIP_API_TOKENS` (JSON array). Không set = auth tắt (dev mode).
- Thu thập giá: `HMIP_COLLECT_MODE` (demo|http). `http` mà không set `HMIP_PRICE_API_BASE` → fallback Tiki API.
- Chain smart PI: `FIRECRAWL_API_KEY`, `SCRAPERAPI_KEY`, `ZENROWS_KEY` (Render `sync: false`).
- Scheduler: `HMIP_AUTOSCAN` (bật/tắt quét nền `hmip_auto_scan` + `hmip_pi_collect`; 21/08 đã gỡ — deploy mặc định `off`), `HMIP_SCAN_INTERVAL_MIN`, `HMIP_PI_COLLECT_MIN` (chu kỳ nếu bật lại).
- **Lịch chạy hằng ngày (giờ VN):**
  - **03:00** — beer-scan `daily-scan.yml` → email 4 hộp (VN 2 + ZH 2, thuần ZH = uythanhhoang+yingxue0510) → push Supabase → notify TG+Discord
  - **03:30** — HMIP `reconcile` (cron `30 20 * * *`) → commit giá → Render auto-deploy
  - **04:00** — HMIP `app-sync` (cron `0 21 * * *`) → wake → `/api/scan-if-stale` (trang chủ) + **`/api/price-intelligence/collect` (blocking — chờ PI xong trước)**
  - **≈05:00** — HMIP `report` (needs: app-sync trong `reconcile.yml`) → `POST /api/price-intelligence/daily-report/send` trên Render → gửi **TG+Discord+Email** với dữ liệu đã nạp
- **Trạng thái Render scheduler (KHÔNG tự chạy, GH Actions điều khiển):** `hmip_auto_scan`=off (`HMIP_AUTOSCAN=off`), `hmip_pi_collect`=off (spr), `hmip_daily_report`=**off mặc định** (`HMIP_DAILY_REPORT=off`) — Render chỉ cung cấp endpoints, workflow là nguồn. User muốn bật nội bộ cho đuidelim qua `HMIP_DAILY_REPORT=on` trên Render (chọn riêng).
- **Email channel (PR #21):** `extensions/pi/email_report.py` HTML bilingual — vi → chubay008+kalihello541; **zh thuần → uythanhhoang+yingxue0510**. Env `EMAIL_VI`/`EMAIL_ZH` ghi đè. `HMIP_EMAIL_REPORT`=on (mặc định). SMTP Gmail SSL; secret `SMTP_APP_PASS`; user `SMTP_USER` (=chubay008@gmail.com).
- **Endpoints:** (1) `GET .../daily-report` JSON; (2) `/text` markdown; (3) `POST .../send` (workflow report); (4) `GET .../topics` (list) + (5) `/topics/timeline?topic_key=` (History); (6) **`POST .../collect` blocking** (app-sync); (7) `POST .../collect-if-stale` (async — vào /pi). Smoke-tested TestClient + CURL smoke (PR #20 61c1e78; PR #21 bổ sung email + report-after-app-sync).
- Auto-scan khi vào trang: `HMIP_AUTO_SCAN_STALE_MIN` (mặc định 5'). Khi user truy cập `/`, `/pi`, `/workspace` → frontend gọi `/api/scan-if-stale` (+ `/api/price-intelligence/collect-if-stale` cho PI) → backend chỉ quét background nếu dữ liệu cũ hơn cửa sổ; fresh → skip (tránh spam Render/credit khi refresh). `0` = luôn quét.
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

## Kiểm thử — lưu ý isolation (PR #5)

- **Scheduler thread leak (đã fix):** test dùng scheduler (`test_autoscan_lifecycle`, `test_api_endpoints`) start `BackgroundScheduler`. `scan_once` quét nhiều SP (68 trong `_DEMO_CATALOG`); nếu teardown `shutdown(wait=False)` không chờ job xong → thread sót chèn SP lạ vào `temp_db` của test sau (race → `test_db_upsert_is_idempotent` fail: 2 rows / tên SP lạ). Fix: (1) `extensions/tests/conftest.py` autouse `_stop_scheduler_after_test` — shutdown + remove_all_jobs + recreate scheduler (APScheduler không restart sau shutdown); (2) `test_autoscan_lifecycle` monkeypatch `_DEMO_CATALOG` thành 2 SP để scan_once <0.5s. Khi thêm test mới dùng scheduler, dùng catalog nhỏ hoặc dựa vào autouse teardown.
- **State notify reset (đã fix):** autouse `_reset_notify_rate_limit` reset state anti-spam cả 2 hệ notify (PI `notifier.py` + scheduler `notifiers/rate_limit.py`) giữa test — tránh state leak khi test đụng notify. Từ PR #9 state notify bền vững qua DB (`pi_notify_state`), nên fixture dùng tmp DB path riêng (`_set_state_db_path`) + reset trước/sau mỗi test để cô lập hoàn toàn (xoá cả cache in-memory VÀ bảng DB). Test persistence dùng `_set_state_db_path(tmp)` + `_state.clear()` để giả lập restart Render.

## Khi sửa đổi — nguyên tắc
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

## Nguồn giá bia — kết quả probe (20/08/2026)

**Chạy được hằng ngày trên GitHub Actions (miễn phí):**
- beer-price-scan (Kamereo anchor, GO!, TGD, BNK, Thế giới đồ uống, Bia Nhập Khẩu, Đại Lộc, East West, Pasteur St, Heart of Darkness, 7 Bridges) → đồng bộ qua `sync_to_hmip.py` ở repo beer-price-scan, secret `HMIP_SYNC_PAT`
- websosanh (adapter `scripts/sources/websosanh.py`, ~28 SKU), Shopee qua Apify `xtracto~shopee-search` (secret `APIFY_TOKEN`, input `country:"vn"`, chặn giá thùng >=150k tránh nhầm combo)
- Reconcile: `scripts/reconcile_prices.py` — merge trung vị + IQR + SOURCE_TRUST + conflict/anomaly flags; SKU map thủ công `config/beer_scan_sku_map.json`. Workflow `.github/workflows/reconcile.yml` 08:00 VN (cron `"0 1 * * *"`).
- App sync (21/08, gộp trong `reconcile.yml` job `app-sync`) 08:30 VN (cron `"30 1 * * *"`, định tuyến bằng `github.event.schedule`) — wake Render rồi trigger `POST /api/scan-if-stale` (giá quét trang chủ, async) + `POST /api/price-intelligence/collect-if-stale` (PI charts workspace) bằng Bearer `HMIP_API_TOKEN` (secret GitHub). Vì scheduler Render (`HMIP_AUTOSCAN=off`) đã tắt, đây là cơ chế định kỳ duy nhất cập nhật bảng giá quét + PI. ⚠️ **KHÔNG dùng `POST /api/run-all`** — endpoint này quét ĐỒNG BỘ ~68 SP, vượt 60s → curl timeout (exit 28); `scan-if-stale` async nền trả ngay + có stale-guard 5'. `workflow_dispatch` chạy cả 2 job (app-sync chỉ khi reconcile success).

**KHÔNG cào được từ runner — đừng thử lại tốn thời gian:**
- Tiki API (403), Sendo API (500), bachhoaxanh/lotte/emart (SPA/geo-block/SSL), tops.vn, kingfoodmart.vn (timeout), annam-gourmet.com, koolbeer.vn, dongson, beercraft.vn, belgo.vn, roosterbeers.com, biacraft, fuzzylogicbrewing.com (rỗng)
- Các site SPA mở được nhưng HTML tĩnh không có giá: chai.vn, vuabia.com, vuabia.net, bianhagau.vn, c-brewmaster.vn, tetebeer.com, thombrewery.vn, steersmanbrewery.com, tlmart.vn, ruoungoaihaigiacat.com, vietgourmet.vn (406), ruousi.vn (giá rác)
- TikTok Shop: actor Apify `pratikdani~tiktok-shop-search-scraper` chỉ trả merchandise in logo bia (quần áo/ly), không phải bia uống → skeleton `apify_tiktok.py` SKIP. Facebook/Instagram/Zalo/YouTube/Telegram: không có cách hợp lệ cào giá (chỉ dùng cho news/sentiment nếu cần)
- bachhoanhaveo.com (**khác bachhoaxanh**) có HTML tĩnh với giá thật → adapter `bachhoanhaveo.py`
- Skeleton `scripts/sources/{tiki,retail_vn,sendo,apify_tiktok}.py` giữ để mở lại khi có proxy/headless browser

**Lưu ý:** `channels{}` trong prices_real.json là dữ liệu seed tĩnh, có giá rác (mmmega 752k, gs25 870k cho cùng Saigon Special) — reconcile lọc bằng IQR, không nên tin giá seed tuyệt đối.

## Cấu hình hệ thống — cập nhật (21/08/2026)

**Branches:**
- HMIP: default `main`
- beer-price-scan: default `main` (đã tạo từ `openhands/data-upload` 20/08 — schedule chỉ chạy trên default branch)

**Secrets (đã set trong GitHub Secrets của từng repo):**
- beer-price-scan: `SMTP_APP_PASS`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`, `DISCORD_WEBHOOK_URL`, `SUPABASE_URL`, `SUPABASE_KEY`, `HMIP_SYNC_PAT` (rotate 22/08)
- HMIP: `APIFY_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`, **`HMIP_API_TOKEN`** (21/08 — cho job app-sync gọi Render API; giá trị = `HMIP_API_TOKEN` trên Render Dashboard)
- **CẢ 2 repo (22/08)**: `TELEGRAM_DONE_BOT_TOKEN` + `TELEGRAM_DONE_CHAT_ID` (=8891619372) — bot thông báo hoàn tất `@Job_tu_dong_email_bao_cao_bot`; `DISCORD_DONE_BOT_TOKEN` + `DISCORD_DONE_CHANNEL_ID` (=1533881868678725696) — bot `AI Lịch quét tự động` → `#general`; `OPENHANDS_API_KEY` — mở session OpenHands Cloud cho auto-remediation

**Supabase (DB bền vững cho app Render):**
- Project `earlqyhtchhfqcxtmivh` (ap-southeast-1, ACTIVE_HEALTHY) chứa 17 bảng: `products`, `price_points` (giá quét trang chủ), toàn bộ `pi_*` (PI workspace).
- Render env `DATABASE_URL` + `HMIP_PI_DATABASE_URL` đều trỏ pooler `aws-0-ap-southeast-1.pooler.supabase.com:6543` (user `postgres.earlqyhtchhfqcxtmivh`) → dữ liệu sống qua mỗi lần redeploy. Đã xác minh 21/08: 68 products, 6.8k price_points, timestamp mới đúng giờ app-sync chạy.
- Project thứ hai `jucxgvonahsqmpszghux` ("beer-price-scan") là DB riêng của repo scan, không dính app HMIP.

**Bot/Token hiện tại:**
- Telegram: `@lich_quet_tu_dong_bot` (token `8836505362:...`, không còn workflow nào gọi từ 22/08) + **`@Job_tu_dong_email_bao_cao_bot`** (id `8946172106`, bot thông báo hoàn tất từ 22/08), chat_id chung `8891619372`
- Discord: App/bot `AI Lịch quét tự động` (App ID `1540215286781706300`), server `chu7's Hermes Server` (`1533881868108169428`), channel `general` (`1533881868678725696`)
- ⚠️ App ID & Public Key của Discord **không phải bot token** — không dùng để gửi tin nhắn. Bot token lấy từ Developer Portal → Bot → Token.
- Render API key cũ `rnd_sBLIS...` **vẫn chưa rotate** — pipeline cũ `run_auto.sh` local dùng (đã bỏ hardcode, cần env khi chạy).

**Pipeline notify (CŨ — đã gỡ khỏi workflow 22/08):**
- ~~beer-scan: notify.py gửi TG + Discord~~ / ~~HMIP reconcile: `scripts/notify_report.py`~~ — cả 2 file vẫn còn trong repo nhưng không còn được workflow gọi. Thay bằng `notify_done.py` (bot mới) + `auto_remediate.py` (khi fail) — xem mục "Quyết định vận hành".

## Báo cáo email hằng ngày (beer-price-scan `send_email.py`, 03:00 VN từ 22/08)

Báo cáo ngành bia gửi qua Gmail SMTP (secret `SMTP_APP_PASS`, sender `chubay008@gmail.com`, BCC):
- **Song ngữ VN + ZH**: `chubay008@gmail.com`, `kalihello541@gmail.com`
- **Chỉ tiếng Trung**: `uythanhhoang@gmail.com`, `yingxue0510@gmail.com`
- Subject: "Báo cáo ngành bia VN 越南啤酒行业报告 – dd/mm/yyyy". Cùng 1 lần quét với dữ liệu sync sang HMIP (build_report.py build từ `data_overrides.json` vừa refresh) → **email = raw scan ngày X; trang web "Giá thật"/"Channel Comparison" = cùng ngày X sau reconcile** (median+IQR nên có thể khác nhẹ, đó là cố ý).
- Nếu đổi danh sách nhận: sửa `RECIPIENTS`/`ZH_ONLY_RECIPIENTS` trong `send_email.py` ở repo beer-price-scan.

## Quyết định vận hành (chốt 21/08/2026, cập nhật 22/08)

- ~~**Giữ nguyên 3 mốc**: 07:30 beer-scan → 08:00 reconcile → 08:30 app-sync~~ → **ĐỔI 22/08: 03:00 beer-scan (cron `0 20 * * *`) → 03:30 reconcile (`30 20 * * *`) → 04:00 app-sync (`0 21 * * *`)** theo yêu cầu user. Khoảng cách 30' giữa các mốc giữ nguyên (buffer cho beer-scan chạy ~20-25').
- **Thông báo hoàn tất qua Telegram + Discord** (22/08): mỗi job kết thúc gửi 1 tin "HOÀN TẤT pipeline" kèm mô tả công việc (`DONE_TASK_DESC`), step `if: always()` cuối mỗi job. Kênh: Telegram bot `@Job_tu_dong_email_bao_cao_bot` (secrets `TELEGRAM_DONE_BOT_TOKEN` + `TELEGRAM_DONE_CHAT_ID`=8891619372) + Discord bot `AI Lịch quét tự động` (secrets `DISCORD_DONE_BOT_TOKEN` + `DISCORD_DONE_CHANNEL_ID`=1533881868678725696, channel `general` server `chu7's Hermes Server`) — đã set ở CẢ 2 repo. Script: `notify_done.py` (beer-price-scan, repo root) + `scripts/notify_done.py` (HMIP). ⚠️ **Discord bắt buộc header `User-Agent: DiscordBot (...)`** — request không UA từ GitHub Actions runner bị Discord trả 403 Forbidden (đã fix, commit e01d618); `notify_report.py` cũ đã có UA nên không dính. Job app-sync của reconcile.yml trước đây KHÔNG có `actions/checkout` → đã thêm (fix f2cec94) vì notify_done.py nằm trong repo. Kênh này là kênh thông báo DUY NHẤT từ 22/08 (commit cd0a94e + beer-price-scan e8d32a6) — đã GỠ step notify cũ (`notify.py` job scan, `notify_report.py` job reconcile) theo yêu cầu user. Script `notify.py`/`notify_report.py` vẫn còn trong repo nhưng không còn được workflow gọi.
- **Auto-remediation khi job fail** (22/08, commit 63cbf65 + beer-price-scan c2710f3): step `if: failure()` cuối mỗi job chạy `auto_remediate.py` (HMIP: `scripts/`; beer-price-scan: repo root) → thu thập step fail + log lỗi qua `gh run view --log-failed` (cần permission `actions: read` — đã thêm vào cả 2 workflow) → gọi OpenHands Cloud API `POST /api/v1/app-conversations` (secret `OPENHANDS_API_KEY`, đã set cả 2 repo) mở session agent với prompt tự-contained: chẩn đoán → lỗi tạm thời thì chỉ `gh run rerun --failed`, lỗi code thì sửa tối thiểu + mở PR branch `fix/auto-remediate-<run_id>` + **AUTO-MERGE CÓ ĐIỀU KIỆN** (chốt 22/08, commit f479b00 + beer-price-scan 2d26b5a): chỉ merge khi đủ 3 điều kiện — (a) CI check PR xanh, (b) rerun workflow lỗi trên branch fix pass (hoặc mô phỏng step fail trong sandbox pass), (c) báo Telegram "đã tự merge PR" kèm link; thiếu điều kiện nào → để PR chờ review tay. Vẫn cấm push thẳng main / đổi secrets / tắt workflow. Workflow có thêm quyền `pull-requests: write` + `checks: read` → báo link run + link session về Telegram/Discord (dùng chung secrets `*_DONE_*`). Script không bao giờ làm fail workflow (mọi lỗi chỉ WARN); hỗ trợ `DRY_RUN=1` để test prompt offline.
- **Set secret GitHub khi token của agent là `ghu_...` (GitHub App user token):** bị 403 "Resource not accessible by integration" khi ghi Actions secrets → cần classic PAT của user + REST API (`GET .../actions/secrets/public-key` → mã hóa libsodium sealed box → `PUT .../actions/secrets/{name}`). Script tham khảo: đã dùng 21/08 set `HMIP_API_TOKEN`.
- **Kiểm tra hệ thống không cần đăng nhập dashboard:** Render API `GET /v1/services/{id}/env-vars` (key `rnd_...`); Supabase Management API `POST /v1/projects/{ref}/database/query` (key `sbp_...`). Hai credential này user cung cấp trong chat 21/08 và đã được khuyên rotate/revoke sau dùng.
- **Chạy thử pipeline không chờ lịch:** Actions → "Reconcile giá đa nguồn" → Run workflow → chạy cả reconcile + app-sync nối tiếp.

**Vấn đề đã fix:**
- beer-scan schedule không chạy → do default branch `openhands/data-upload`, không có `main`. Fix: tạo `main` + đổi default (20/08).
- `HMIP_SYNC_PAT` hết hạn (22/08) → bước "Sync scan data to HMIP repo" fail "Invalid username or token". Fix: rotate PAT mới vào secret. ⚠️ **`gh run rerun --failed` KHÔNG cứu được sync**: rerun checkout lại SHA cũ → step "Commit & push" bị remote reject (đã có commit cùng ngày) → step sync bị skip. Cách đồng bộ bù: clone beer-price-scan@main về local rồi chạy `HMIP_SYNC_PAT=... python3 sync_to_hmip.py` (script chỉ đọc file JSON/report ở repo root).
- **GitHub Actions free tier trễ lịch 2,5–3h** vào khung UTC 00:00–04:00 (tức 07:00–11:00 VN): 3 mốc 07:30/08:00/08:30 VN thực tế chạy ~10:13/10:26/10:55 VN (quan sát 21–22/08). Pipeline vẫn đúng thứ tự, email đến ~10:30–11:00 VN. Đây là giới hạn SLA của GitHub, không phải lỗi pipeline.

## Tự động hằng ngày — tổng hợp lịch (27/08/2026)

**Pipeline healthcheck (27/08, PR #24 + beer-price-scan PR #1):** dead man's switch
`scripts/pipeline_healthcheck.py` — kiểm tra run theo lịch hôm nay (theo ngày VN);
thiếu → hỏi githubstatus API; đang sự cố → alert TG/Discord + session OpenHands;
đã hồi → tự `workflow_dispatch` chạy bù; chống trùng khi đã dispatch. Cron 3 lượt/ngày
(04:45/07:45/10:45 VN, `startsWith(schedule,'45 ')`). Bắt nguồn từ vụ 26-27/08:
GitHub Actions miss run theo lịch và KHÔNG tự chạy bù sau hồi phục.

**Market intel nguồn uy tín (beer-price-scan PR #1):** `market_intel.py` qua Google
News RSS theo nguồn (NielsenIQ/Nielsen, Kantar, IPSOS, Metric.vn, Euromonitor, Q&ME,
tin ngành bia VN + lọc keyword) → `market_intel.json` → section 10 trong email
(`build_report.py::market_intel_section`, song ngữ VN/ZH, ghi rõ nguồn/bản quyền).
Không scrape nội dung trả phí — chỉ tin công khai.

**Đề nghị 2 (27/08) — đánh giá + khuyến nghị, KHÔNG code:**
- **Vấn đề thật**: `bachhoaxanh.com` (API Zuul bị proxy `zuul.reverse` chặn → 403 kể cả `FIRECRAWL/ScraperAPI/ZenRows chain`), `cooponline.vn` (SPA render JS — HTML trắng, Jina 403), Còn các site khác OK.
- **Hướng đúng** (không Hysteria/CloakBrowser): mở rộng Apify actors (đã có `xtracto~shopee-search` làm mẫu — actor bên 3 chịu trách bypass) cho Lazada + Bách Hóa Xanh; hoặc nâng cấp plan ScraperAPI/ZenRows (premium proxy) cho Akamai/BHX.
- **Thực tế ổn định**: kênh fail thì kênh khác gánh + fallback `prices_real.json` (report không trắng); Tiki API public OK; email vẫn đủ dữ liệu. Không cần cố ép kênh chặn 403 → giữ graceful degradation.
- **Action cho user**: (1) Đăng ký affiliate Tiki/Lazada/Shopee Open Platform có phí nhưng API chính thức ổn định nhất; (2) Thêm Apify actor với khi quota đủ; (3) Nâng plan ZenRows/ScraperAPI (~50-100 USD/tháng) nếu muốn BHX/Coop hiện hành ổn định.

**Two cụm chạy mỗi ngày sau khi PR #20 lên (giờ VN, nguồn cron chuẩn tại `.github/workflows/reconcile.yml` + `extensions/api.py`):**

| Giờ VN | Lớp | Job | Hành động |
|---|---|---|---|
| 03:00 VN | GH Actions (beer-price-scan) | `daily-scan.yml` | Quét nguồn giá → email 4 hộp thư (VN 2 + ZH 2, thuần ZH = uythanhhoang+yingxue0510) → push Supabase (repo scan) → notify TG+Discord |
| 03:30 VN | GH Actions (HMIP) | `reconcile.yml` job `reconcile` (cron `30 20 * * *`) | `reconcile_prices.py` → commit `prices_real.json` → Render auto-deploy |
| 04:00 VN | GH Actions (HMIP) | `reconcile.yml` job `app-sync` (cron `0 21 * * *`) | Wake Render → `POST /api/scan-if-stale` + **`POST /api/price-intelligence/collect` (blocking — chờ PI xong)** |
| **≈05:00 VN (sau app-sync)** | GH Actions (HMIP) | `reconcile.yml` job `report` (needs: app-sync) | `POST /api/price-intelligence/daily-report/send` trên Render → gửi **TG+Discord+Email** |

- Render scheduler (off by default): `hmip_auto_scan`, `hmip_pi_collect`, `hmip_daily_report` (KHÔNG chạy — workflow điều khiển). User muốn bật nội bộ (lựa chọn riêng) qua `HMIP_DAILY_REPORT=on`.
- `reconcile.yml` giờ 3 job: `reconcile` (03:30) → `app-sync` (04:00) → **`report` (needs: app-sync)**.
- ⚠️ **Daily report không dùng `POST /api/run-all` nào** — chỉ qua workflow; dev muốn chạy tay dùng `POST /api/price-intelligence/daily-report/send` + optional `?date=`.

## Nhật ký phiên 26/08/2026 — PI baseline từ Job 1 (stability phase 2)

- **Vấn đề (báo cáo trắng):** collect phụ thuộc tiers → fail → tỉ lệ `changed=0` → events rỗng → report toàn section = 0.
- **Giải:** commit `de56b85` thêm `seed_baseline_from_master()` trong `persistent_collector.collect_smart()`. Trước khi crawl: nếu DB chưa có `real_seeded` marker → nạp 72 SKU × kênh best từ `knowledge/master/prices_real.json`. Lần 2+ skip (idempotent). Mọi tầng fetch sau đó có baseline để so → changed delta != 0.
- **Kênh động (`_channels_from_real_prices`):** từ prices_real thay vì hardcode 5 kênh default → FK `pi_channels` mọi kênh map được.
- **Catalog giàu hơn:** thêm 4 sản phẩm thiếu (`P888`,`PCN_OB`,`PCN_SE`,`PRUS_B0`) vào `DEFAULT_PRODUCTS` (68→72); sửa test `len(DEFAULT_PRODUCTS)` thay vì hardcode 68.
- **brand_id ≠ "" (SQLite FK ON) khi brand rỗng → fallback `"AGG"` (Aggregate) hoặc brand từ product.** Sửa `store_price_point`.
- **`api._pi_collect_job` harden:** try/except per-tier collect + detect_events (log.exception, không crash scheduler).
- **Tests:** baseline idempotent + has_real_prices; 154 pass.
- **Pipeline ngày:** Job 1 scan 03:00 (beer-price-scan); HMIP `reconcile` 03:30 commit prices_real.json → Render auto-deploy; `app-sync` 04:00 PI collect sẽ kèm baseline; `report` ~05:00 email luôn render được snapshot kể cả khi events empty.

## Nhật ký phiên 22/08/2026 — đại tu pipeline thông báo & tự xử lý lỗi

**Bối cảnh:** user hỏi "vì sao chưa nhận email" → phát hiện GitHub Actions free tier trễ 2,5–3h ở khung UTC 00:00–04:00 (không phải lỗi). Sau đó user yêu cầu chuỗi thay đổi lớn.

**Đã làm (theo thứ tự):**
1. Chẩn đoán độ trễ GitHub Actions (xem mục "Vấn đề đã fix").
2. Rotate secret `HMIP_SYNC_PAT` (PAT cũ hết hạn) + đồng bộ bù dữ liệu scan vào HMIP bằng tay (clone beer-price-scan → chạy `sync_to_hmip.py` local — vì `gh run rerun` checkout SHA cũ không cứu được).
3. Đổi lịch 3 cron job: 03:00 scan (`0 20 * * *`) → 03:30 reconcile (`30 20 * * *`) → 04:00 app-sync (`0 21 * * *`) VN.
4. Thêm tin "HOÀN TẤT pipeline" qua bot Telegram mới `@Job_tu_dong_email_bao_cao_bot` — script `notify_done.py` (cả 2 repo), step `if: always()`.
5. Mở rộng thông báo hoàn tất sang Discord (bot `AI Lịch quét tự động` → `#general`). Fix lỗi Discord 403: bắt buộc header `User-Agent: DiscordBot (...)`.
6. Gỡ nhóm thông báo cũ (`notify.py`, `notify_report.py`) khỏi workflow theo yêu cầu user — chỉ còn bot mới.
7. **Auto-remediation (Lớp 2):** step `if: failure()` chạy `auto_remediate.py` → mở session OpenHands Cloud tự chẩn đoán/xử lý (hoàn toàn cloud, user không cần mở máy). Ban đầu chỉ mở PR chờ review → user chốt phương án (b) **auto-merge có điều kiện** (CI xanh + rerun/verify pass + báo Telegram sau merge).
8. Set secrets qua REST API + classic PAT của user: `TELEGRAM_DONE_*`, `DISCORD_DONE_*`, `OPENHANDS_API_KEY` (cả 2 repo).
9. Test thực tế: 4 lần workflow_dispatch trên HMIP — phát hiện & fix 2 bug (app-sync thiếu `actions/checkout` → f2cec94; Discord thiếu UA → e01d618). DRY_RUN auto_remediate với run fail thật 32552326709: nhận diện đúng step + log.

**Commits chính:** beer-price-scan `1d4ec81→d7d844e→e8d32a6→c2710f3→2d26b5a`; HMIP `d532342→9b39929→f2cec94→b940e58→b7e642f→efe8418→e01d618→cd0a94e→1c1dec6→63cbf65→f266a19→f479b00→291daa0`.

**Chờ theo dõi 23/08:** lần chạy đầu tiên theo lịch mới (03:00–04:30 VN) — kiểm chứng: độ trễ GitHub Actions ở khung giờ mới, email ~03:25, 3+3 tin hoàn tất, và auto-remediation nếu có job fail.

**Credentials đã lộ trong chat (đã khuyên rotate):** PAT `ghp_daJn...` (đã dùng set secrets), Discord bot token `MTU0MDIx...`, Telegram bot token mới `8946172106:...`. Các giá trị này đều đã nằm an toàn trong GitHub Secrets — rotate dashboard-side rồi cập nhật lại secrets khi user sẵn sàng.
