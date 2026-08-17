# Open Questions — Resolved (2026-08-04)

Tracks resolution of the open questions carried across
`SPRINT_3_STATUS.md`, `SPRINT_4_STATUS.md`, and `SPRINT_6_STATUS.md`.
Those files are left as-is (historical record of when each question
was raised); this file is the current, authoritative answer.

## 1. `runtime_version`/`kernel_version` values — RESOLVED

- `runtime_version` is now tied to the real installed package version
  (`importlib.metadata.version("hmip")`, matching `pyproject.toml`'s
  `[project].version`), falling back to a hardcoded `"0.1.0"` only if
  package metadata isn't discoverable. Implemented in
  `shared/constants.py::_resolve_runtime_version()`.
- `kernel_version` is a separate hardcoded constant, `"1.0.0"`,
  representing this codebase's own core-runtime-kernel release train
  — bump it manually in `shared/constants.py` when kernel behavior
  changes in a way worth tracking. Not tied to `pyproject.toml`.
- Both remain overridable per-run via `HMIP_RUNTIME_VERSION`/
  `HMIP_KERNEL_VERSION` env vars (Sprint 6), which take priority over
  either default.

## 2. `PersistentLineageTracer` default path — RESOLVED

- Defaults to `knowledge/dynamic/lineage/lineage.jsonl` (relative to
  the process's current working directory — same convention as
  `platform_/bootstrap.py`'s `HMIP_REPORT_DIR`/`HMIP_CONFIG_PATH`
  defaults) when no `path` is passed to the constructor. Implemented
  in `core/lineage.py::PersistentLineageTracer.DEFAULT_PATH`.
- `core.workflow_engine.WorkflowEngine`'s own default tracer is
  **unchanged** — it still defaults to `InMemoryLineageTracer()`, not
  `PersistentLineageTracer()`. Switching the engine's default to
  write to disk automatically was a separate decision that wasn't
  asked for and would have real consequences (every test using the
  default constructor would start writing real files unless every
  such test were updated to redirect it) — callers who want
  persistence still pass `lineage_tracer=PersistentLineageTracer()`
  explicitly.

## 3. Python version for local dev — RESOLVED (no change)

- `pyproject.toml`'s `requires-python = ">=3.12"` stays as-is —
  **not** pinned to `>=3.12,<3.13`. The local dev machine keeps
  running Python 3.14.5 via `uv`.
- This only concerns local development. The container (`Dockerfile`)
  was already unambiguously pinned to `python:3.12-slim` in Sprint 6,
  independent of this decision.

## 4. Ontology wired into PRC-001 — RESOLVED

- Added a new `enrich` task to `WF-PRC-001.yaml`, between `validate`
  and `compare`: `collect → extract → validate → enrich → compare →
  decide → alert`.
- `domains/beer/pricing/skills/enrich_price.py::enrich_with_ontology()`
  cross-references the validated price record against
  `knowledge.ontology` (loaded from the real `knowledge/master/*.json`
  files):
  - Rejects an unknown `product_id` (`WorkflowExecutionException`,
    code `ENRICH_PRICE_UNKNOWN_PRODUCT`).
  - Rejects an extracted `brand` that doesn't match the ontology's
    authoritative `Brand.name` for that product (code
    `ENRICH_PRICE_BRAND_MISMATCH`) — a genuine data-quality check, not
    a formality.
  - Fills in `sku` from the ontology when extraction didn't provide
    one (PRC-001's mock collect payload never does).
- `registrar.py` registers `enrich`'s handler and rollback (a no-op,
  like most of PRC-001's other tasks — see `SPRINT_5_STATUS.md`'s
  compensation section for why that's fine).
- Tests: `domains/beer/pricing/tests/test_enrich_price.py` (isolated
  unit tests plus one test loading the real shipped master data),
  plus updated lineage/event/compensation assertions across
  `tests/workflow/test_prc_001_*.py` to include the new 7th step.
- **Bug found and fixed on first real test run**: `enrich_price.py`'s
  `_MASTER_DIR` used `Path(__file__).resolve().parents[3]`, which
  resolves to `domains/` (the file is 4 levels below repo root:
  `domains/beer/pricing/skills/enrich_price.py`), not the repo root —
  every real-workflow PRC-001 test failed with `KnowledgeValidationException:
  master data file not found`. Fixed to `parents[4]`. All 268 tests
  pass after the fix.

## Still open (not addressed this round)

None remaining from the tracked list.

---

## Post-launch fixes (2026-08-17, PR #12 + #13)

Các fix này nằm ngoài danh sách "open questions" gốc (chỉ theo dõi quyết định
kiến trúc Sprint 3-6), nhưng được ghi lại đây vì chúng sửa lỗi chức năng
thật của lớp `extensions/` (Price Intelligence + notify) — ảnh hưởng trải
nghiệm người dùng và được tài liệu `AGENTS.md` + `docs/CODEBASE_OVERVIEW.md`
tham chiếu.

### PR #12 — Brand "Unknown" + Promotion Intelligence + channel expansion (merged 53845ab)

- **Brand "Unknown" trong Competitor Comparison / Price Index (by Brand):** JOIN
  `pi_brands` qua `pi_products.brand_id` (không qua `pi_observations.brand_id`
  — cột observation hay rỗng). `pi_store.migrate_brand_ids()` backfill
  `brand_id` observation từ `pi_products.brand_id` + xoá brand rỗng/Unknown
  (idempotent, wire vào `api.py` lifespan startup). Test
  `test_migrate_brand_ids_backfill_empty` (assertion "pre" theo fix product-join).
- **Promotion Intelligence:** `analytics.promotion_by_brand` +
  `promotion_timeline` → chart Promotion Intelligence (UI `/pi`).
- **Channel expansion:** channel registry mở rộng TIKI/SHOPEE/LAZADA →
  **+TIKTOK/GRABMART**; `HMIP_CHANNELS` mặc định 5 kênh (trước chỉ `tiki`);
  seed demo `_CHANNEL_FACTOR` mở rộng 18 kênh (factor thực tế: Shopee 0.90 rẻ
  nhất, Circle K 1.10 đắt nhất).
- **Drop "Giá tham chiếu (lon)" line:** khỏi message notify cả Hệ 1
  (`pi/notifier.py::_format`) lẫn Hệ 2 (`notifiers/telegram.py`+`discord.py`)
  theo yêu cầu user. `base_price` vẫn trong signature notify (caller truyền) nhưng
  không render.
- CI xanh; +5 test PI (brand Unknown/promo/channels/migrate_brand_ids).

### PR #13 — Alert price accuracy: per-lon compare + clamp pack + fix -98.67% false alerts (merged 02fa68c)

**Vấn đề:** tin nhắn cảnh báo (Telegram & Discord, Hệ 1 PI collect) hiện số sai
rõ ràng:
- "Giá thùng (450 lon): 517,500,000₫" — pack_size=450 (vô lý cho bia)
- "Giá (lon): 1,150,000₫ → 15,333₫/lon (-98.67%)" — so sánh giá THÙNG vs giá
  LON LẺ rồi gán nhãn cả hai là "/lon" (artifact pack-mismatch)

Giá đúng phải là: thùng 24 lon @ 1,150,000₫ → **47,917₫/lon**, so lon lẻ
15,333₫ = **-68%** (không phải -98.67%).

**3 root cause + fix:**
1. `_parse_pack_volume` (collectors.py, path API Tiki) regex `(\d+)\s*lon`
   bắt mọi số trước "lon" → "Combo 450 lon"=450, "Lon 330"=330. **Fix:** clamp
   pack về `{6,12,24}` (lon lẻ=1); số lạ reject, "thùng"→24, còn lại→1. Khớp
   `price_extract._detect_pack` (`[2,48]`) + `_infer_pack_from_price` (snap
   `{6,12,24}`).
2. `store_price_point_if_changed` (persistent_collector.py) so **raw
   `effective_price`** giữa observation có pack khác nhau → -98.67% giả. **Fix:**
   so sánh + alert trên **giá/LON** (`effective_price / pack_quantity` =
   `norm.price_per_unit`). `_latest_observation` JOIN `pi_skus.pack_quantity` +
   lấy `unit_price` (giá/LON đã chuẩn hoá lúc insert); DB cũ thiếu `unit_price`
   → suy lại `effective_price/pack`. Alert mang per-lon old/new → change_pct thật.
3. `notifier._format` gán nhãn raw là "VND/lon" + "Giá thùng" = per-lon ×
   pack_size (→ "(1 lon)" / "(450 lon)" vô lý). **Fix:** alert giờ mang giá/LON;
   message hiện `Giá/LON: ...₫ → ...₫/lon (X%)` + `Giá thùng (24 lon): ...` (=
   per-lon × 24, thùng bia VN tiêu chuẩn, không phụ thuộc pack item cào được).

**Test:** `test_parse_pack_volume_clamps_absurd_pack` (pack clamp),
`test_per_lon_comparison_avoids_pack_mismatch_false_alert` (tái lập -98.67%→-68%),
`test_alert_message_shows_per_lon_and_standard_box` (message accuracy). Suite
**415 pass / 1 skip**, coverage 94.28%. CI xanh.

**Lưu ý:** DB cũ (pre-fix) thiếu `unit_price` → code suy lại từ
`effective_price / pack_quantity` (từ `pi_skus`), nên migration ngầm, không cần
rebuild. Hệ 2 (PRC-001 scheduler, `notifiers/telegram.py`/`discord.py`) dùng
`base_price` từ `_BASE_PRICES` (lon) — đã đúng đơn vị, không bị lỗi pack-mismatch;
không đụng.
