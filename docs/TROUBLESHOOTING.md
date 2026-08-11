# TROUBLESHOOTING — HMIP

## `ModuleNotFoundError: No module named 'pytest'` / `.venv/bin/python: No such file`

**Nguyên nhân:** `.venv/` trong repo là virtualenv **Windows** — chỉ có `.venv/Scripts/*.exe`, không có `.venv/bin/`. Không dùng được trên Linux/macOS. `[VERIFIED]`

**Cách xử lý:**
```bash
python3 -m venv /tmp/hmip-venv
/tmp/hmip-venv/bin/pip install -e ".[dev]"
/tmp/hmip-venv/bin/python -m pytest -q
```

## Test collection lỗi vì package `platform`

**Nguyên nhân:** package từng tên `platform/`, đụng module `platform` của stdlib → pytest không collect được test nào import từ nó.

**Trạng thái:** đã sửa ở Sprint 6, đổi thành `platform_/` (`ADR_010_platform_package_rename.md`). Nếu gặp lại, kiểm tra không còn thư mục `platform/` mồ côi (hiện **không còn** — đã xác minh).

## Bootstrap FAILED

Report **luôn** được ghi kể cả khi fail — đọc nó trước:
```bash
cat "$HMIP_REPORT_DIR"/bootstrap_*.json    # mặc định ./reports
```
Trường `task_results[]` chỉ đúng bước hỏng kèm `error`. Các code thường gặp:

| Code | Ý nghĩa |
|---|---|
| `BOOTSTRAP_NO_CONFIG_PATHS` | `config_paths` rỗng |
| `CONFIG_FILE_NOT_FOUND` | thiếu file trong `$HMIP_CONFIG_PATH` (mặc định `./config`) |
| `CONFIG_INVALID_YAML` | YAML sai cú pháp |
| `CONFIG_UNRESOLVED_VARIABLE` | `${VAR}` không có default và biến không tồn tại |
| `CONFIG_STORAGE_FAILURE` | file tồn tại nhưng không đọc được (quyền, I/O) |
| `REGISTRY_DUPLICATE_TASK` | registrar đăng ký trùng tên |

## Readiness luôn trả READY dù bootstrap vừa fail

**Nguyên nhân:** `clear_ready()` không được gọi ở đâu (`readiness.py` L57-65). Marker file từ lần chạy thành công trước vẫn còn.

**Xử lý:** xoá thủ công `$HMIP_READY_FILE` (mặc định `<tmp>/hmip_ready`) trước khi chạy lại. Với `emptyDir` trên K8s thì không phát sinh.

## `HMIP_LOG_LEVEL` đặt rồi mà log không đổi

**Không phải lỗi cấu hình của bạn** — đây là gap trong code. `configure_logging()` được gọi không tham số nên luôn dùng `INFO`; giá trị `logging.level` trong config **không được đọc**. Xem F-04.

## Workflow không chạy khi start container

**Đúng như thiết kế hiện tại**, không phải bug: ENTRYPOINT chỉ là `python -m platform_.bootstrap`, và bootstrap chỉ đăng ký một task `noop`. `WorkflowEngine` chưa được nối vào entrypoint nào. Xem F-01.

## `COLLECT_PRICE_SOURCE_UNAVAILABLE`

Adapter là mock, `_MOCK_SOURCE_DATA` chỉ có đúng một khoá `("P123", "shopee")`. Bất kỳ `product_id`/`source` nào khác đều raise. `[VERIFIED]` `collect_price.py` L25-35.

## `ENRICH_PRICE_BRAND_MISMATCH`

Brand từ extract không khớp `Brand.name` trong ontology. Ontology là nguồn sự thật — kiểm tra `knowledge/master/brands.json` và `products.json`.

## Lineage file trống dù workflow đã chạy

`WorkflowEngine` mặc định dùng `InMemoryLineageTracer` (mất khi thoát process). Muốn ghi file phải inject:
```python
WorkflowEngine(..., lineage_tracer=PersistentLineageTracer())
```
`[VERIFIED]` `workflow_engine.py` L79-81.

## Report/lineage mất sau khi pod K8s kết thúc

`job.yaml` dùng `emptyDir` cho cả 3 mount. Muốn giữ lại thì đổi sang PVC. Xem F-03.
