# VERIFICATION_REPORT — HMIP

> Phase 3 output. Đây là tài liệu **quan trọng nhất** theo workflow (mục 10: *"phase quan trọng nhất để tăng độ chính xác"*).
> Phương pháp: chạy thật test suite + entrypoint, grep đối chiếu symbol, so README/spec với source.

## A. Kiểm chứng bằng thực thi

| Hạng mục | Lệnh | Kết quả | Trạng thái |
|---|---|---|---|
| Test suite | `pytest -q` | **268 passed**, 3.24s | `[VERIFIED]` |
| Coverage gate | `--cov-fail-under=80` | **94.07%** — đạt | `[VERIFIED]` |
| Bootstrap CLI | `python -m platform_.bootstrap` | exit 0, `steps=8`, report JSON được ghi | `[VERIFIED]` |
| Health CLI | `python -m platform_.health` | `HEALTHY`, exit 0 | `[VERIFIED]` |
| Readiness CLI | `python -m platform_.readiness` | `READY`, exit 0 | `[VERIFIED]` |

Lưu ý môi trường: `.venv/` trong repo là **virtualenv Windows** (chỉ có `Scripts/*.exe`, không có `bin/`), không dùng được trên Linux. Đã tạo venv sạch ở `/tmp/hmip-venv` — **không sửa gì trong repo** (tuân thủ mục 2.3 của workflow).

## B. Kiểm chứng symbol & file reference

Mọi symbol được nhắc trong tài liệu Phase 4 đều đã grep xác nhận tồn tại:

| Claim | Symbol | Trạng thái |
|---|---|---|
| Kernel không phụ thuộc domain | `core/` không import `domains.*` | `[VERIFIED]` grep 0 kết quả |
| Registrar đăng ký 7 task | `register_prc_001_tasks` gọi `registry.register()` 7 lần | `[VERIFIED]` `registrar.py` L55-107 |
| 7 task khớp 7 node YAML | collect/extract/validate/enrich/compare/decide/alert | `[VERIFIED]` khớp 1-1 giữa `registrar.py` và `WF-PRC-001.yaml` |
| Ontology chỉ dùng ở enrich | `knowledge.ontology` chỉ được import bởi `enrich_price.py` | `[VERIFIED]` grep |
| Không có DB/HTTP | không có driver/framework nào trong deps hay import | `[VERIFIED]` |

## C. Findings

### F-01 — `[CONTRADICTION]` Workflow engine không được nối vào bất kỳ entrypoint nào

**Mức độ: cao.** Đây là khoảng cách lớn nhất giữa "kiến trúc trên giấy" và "hệ thống đang chạy".

Bằng chứng:
- `WorkflowEngine(...)` được khởi tạo tại **16 vị trí, tất cả đều nằm trong `tests/`** — grep xác nhận, 0 vị trí trong `core/`, `platform_/`, `domains/`.
- `register_prc_001_tasks` chỉ có **1 caller: `tests/workflow/test_prc_001_end_to_end.py` L31**.
- `platform_/bootstrap.py:main()` chỉ đăng ký `_register_demo_tasks` — một task `noop` với `handler = lambda *_args: {}` (L60-66).
- `Dockerfile` ENTRYPOINT = `python -m platform_.bootstrap`.

Hệ quả: **chạy container HMIP sẽ chỉ bootstrap rồi thoát. WF-PRC-001 không bao giờ được thực thi trong production.** Toàn bộ domain layer chỉ sống trong test.

Không tự sửa (mục 2.3). Cần quyết định của con người.

### F-02 — `[CONTRADICTION]` Tài liệu deployment tham chiếu đường dẫn đã bị đổi tên

`deployment/docker-compose.yml` L3 và `deployment/kubernetes/job.yaml` L2 vẫn ghi `platform/bootstrap.py`. Package đã đổi thành `platform_/` từ Sprint 6 (`ADR_010_platform_package_rename.md`). Chỉ là comment nên không gãy runtime — các trường `test:`/ENTRYPOINT thực tế đã dùng `platform_.` đúng. Mức độ: thấp (chỉ gây nhầm cho người đọc).

### F-03 — `[VERIFIED]` `emptyDir` làm mất chính dữ liệu mà code cố ghi bền vững

`job.yaml` L38-44 mount `/app/reports`, `/app/data`, `/app/knowledge/dynamic` bằng `emptyDir` → xoá sạch khi pod kết thúc. Trong khi đó `PersistentLineageTracer` được viết riêng để ghi bền vững qua các lần restart (`lineage.py` L107-130), và `docker-compose.yml` thì dùng bind mount thật (`./volumes/...`). Hai môi trường deploy có ngữ nghĩa persistence **khác nhau**. Có thể là chủ ý (Job là ephemeral), nhưng không tài liệu nào nói rõ.

### F-04 — `[PARTIALLY VERIFIED]` Config được nạp nhưng phần lớn không được đọc

`ConfigLoader` merge cả 3 file YAML thành `FrozenConfig`. Nhưng grep cho thấy **không có code nào đọc** các khoá `logging.level`, `logging.redact_fields`, `container.*`, `health_check.*`, `resources.*` từ config object. Cụ thể:
- `configure_logging()` được gọi **không tham số** (`bootstrap.py` L157) → luôn dùng `level=logging.INFO` mặc định, **bỏ qua** `HMIP_LOG_LEVEL` / `config/logging.yaml`.
- `redact_fields` khai báo trong YAML nhưng **không có logic redact nào tồn tại** trong `observability.py`.

Nghĩa là: cấu hình logging là *khai báo mang tính tài liệu*, chưa có hiệu lực thực thi. Đây là rủi ro an toàn nhẹ — người vận hành có thể tin rằng secret đang được redact khỏi log, thực tế thì không.

### F-05 — `[VERIFIED]` `ConfigLoader.validate()` gần như không validate gì

`config.py` L96-100: chỉ kiểm tra `isinstance(config, dict)` — mà giá trị này luôn là dict do `merge()` đảm bảo. Không có schema validation cho config. Docstring không nói đây là stub (khác với `_resolve_secrets` có ghi rõ "pass-through stub"), nên dễ gây hiểu nhầm về mức độ bảo vệ.

### F-06 — `[VERIFIED]` Biến môi trường khai báo nhưng không dùng

`HMIP_DATA_DIR` có trong `.env.example` và được `09_Deployment_Guide.md` liệt kê, nhưng **không code nào đọc**. Chính `.env.example` L28-30 đã tự thừa nhận điều này một cách trung thực. Không phải lỗi — chỉ ghi nhận.

### F-07 — `[VERIFIED]` Compensation là cơ chế thật với nội dung rỗng

Cả 7 `make_*_rollback()` đều trả closure `return None`. Cơ chế được test đầy đủ (`test_prc_001_compensation.py`), nhưng chưa task nào có side effect thật để hoàn tác. `registrar.py` docstring tự nêu rõ. Ghi nhận để không ai hiểu nhầm là "hệ thống đã có rollback thật".

### F-08 — `[VERIFIED]` Build artifact bị commit

`.coverage` (114KB) nằm trong repo.

## D. Bảng phân loại tổng hợp

| Nhãn | Số lượng | Ghi chú |
|---|---:|---|
| `[VERIFIED]` | phần lớn claim kiến trúc | có file + symbol + kết quả chạy thật |
| `[CONTRADICTION]` | 2 | F-01 (cao), F-02 (thấp) |
| `[PARTIALLY VERIFIED]` | 1 | F-04 |
| `[INFERRED]` | 1 | ý định đa domain |
| `[UNKNOWN]` | 1 | lý do WorkflowEngine chưa được nối |

## E. Điểm mạnh cần ghi nhận

Không chỉ tìm lỗi — những điều codebase này làm tốt hơn mức trung bình:

1. **Docstring trung thực bất thường.** Gần như mọi giới hạn đều được chính source tự khai báo (stub, no-op, "not currently called", "deferred"). Rất hiếm gặp — điều này làm việc audit dễ hơn nhiều.
2. **Ranh giới lỗi nhất quán** — lỗi nghiệp vụ trả result, lỗi cấu trúc/hạ tầng raise. Không lẫn lộn.
3. **Tách trách nhiệm sạch** — chỉ `Planner` được suy luận thứ tự; chỉ `DecisionEngine` sở hữu threshold; `compare_price` thuần transform.
4. **Coverage 94% với chaos test** (disk full, network timeout, deadlock, storage failure) — vượt xa mức thường thấy ở dự án giai đoạn này.

## F. Khuyến nghị (KHÔNG tự thực hiện — chờ human review)

| # | Việc | Ưu tiên |
|---|---|---|
| 1 | Quyết định F-01: thêm CLI `python -m platform_.run_workflow`, hay ghi rõ workflow chỉ dành cho test | Cao |
| 2 | Nối `HMIP_LOG_LEVEL`/`config/logging.yaml` vào `configure_logging()`, hoặc bỏ khỏi config | Cao (F-04) |
| 3 | Hiện thực `redact_fields` hoặc xoá khai báo để tránh cảm giác an toàn giả | Cao (F-04) |
| 4 | Sửa 2 comment `platform/` → `platform_/` | Thấp (F-02) |
| 5 | Gỡ `.coverage` và `.venv` (Windows) khỏi repo, thêm `.gitignore` | Thấp |
| 6 | Ghi rõ chủ ý ephemeral của `emptyDir` trong `job.yaml` | Thấp (F-03) |
