# INTEGRATIONS — HMIP

## Tổng kết

`[VERIFIED]` **Không có external integration nào.** Không HTTP client, không SDK, không message queue, không cloud service, không LLM provider, không database.

Bằng chứng: dependency runtime chỉ gồm 3 gói — `pyyaml`, `structlog`, `jsonschema` (`pyproject.toml` L6-10). Không gói nào có khả năng I/O mạng.

## Các điểm ĐÁNG LẼ là integration, hiện là mock/stub

### 1. Nguồn dữ liệu giá (Shopee / e-commerce)

```text
Service:        Nguồn giá bên ngoài (Shopee)
Purpose:        Lấy giá bia thô
Used by:        domains/beer/pricing/skills/collect_price.py::CollectPriceAdapter.fetch
Authentication: Không có
Configuration:  Không có
Trạng thái:     MOCK — dict `_MOCK_SOURCE_DATA` in-memory, đúng 1 bản ghi ("P123","shopee")
Failure handling: key không khớp → WorkflowExecutionException code COLLECT_PRICE_SOURCE_UNAVAILABLE
Evidence:       collect_price.py L25-58
```

Ranh giới adapter được thiết kế đúng (`BaseAdapter` protocol: `fetch()`/`health()`), chỉ là chưa có implementation thật cắm vào.

### 2. LLM extraction

```text
Service:        LLM provider (chưa chọn)
Purpose:        Trích xuất trường có cấu trúc từ payload thô
Used by:        domains/beer/pricing/skills/extract_price.py::ExtractPriceSkill.run
Trạng thái:     THAY THẾ — parser tất định thay cho LLM
Prompt contract: domains/beer/pricing/prompts/extract_price.md (tồn tại, chưa được code đọc)
Evidence:       extract_price.py docstring; prompt file có mục "Implementation note"
```

Chưa có hạ tầng gọi LLM trong core runtime. `[VERIFIED]`

### 3. Kênh thông báo (alert)

```text
Service:        Kênh notification (chưa chọn)
Purpose:        Gửi cảnh báo khi decision != IGNORE
Used by:        domains/beer/pricing/skills/alert_price.py
Trạng thái:     MOCK — handler trả dict MÔ TẢ thông báo, không gửi đi đâu
Failure handling: rollback là no-op; comment ghi rõ khi có kênh thật thì cần gửi retraction
Evidence:       alert_price.py L14-27, L30-41
```

### 4. Secret provider

```text
Service:        Secret provider (Vault / cloud secret manager — chưa chọn)
Purpose:        Giải mã secret trong config
Used by:        core/config.py::ConfigLoader._resolve_secrets
Configuration:  HMIP_SECRET_PROVIDER (khai báo, không được đọc)
Trạng thái:     STUB pass-through — trả nguyên data, không làm gì
Evidence:       config.py L166-168
```

## Persistence "integration" duy nhất: filesystem

| Đích | Ghi bởi | Định dạng |
|---|---|---|
| `reports/bootstrap_<uuid>.json` | `platform_/bootstrap.py:_write_bootstrap_report` | JSON, indent 2 |
| `knowledge/dynamic/lineage/lineage.jsonl` | `core/lineage.py:PersistentLineageTracer` | JSON Lines, append-only |
| marker readiness (temp dir mặc định) | `platform_/readiness.py:mark_ready` | text `"ready\n"` |

Lưu ý: `WorkflowEngine` mặc định dùng `InMemoryLineageTracer`, **không** dùng bản persistent — muốn ghi file phải inject thủ công (`workflow_engine.py` L79-81).
