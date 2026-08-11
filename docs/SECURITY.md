# SECURITY — HMIP

> Đây là **source-based security documentation**, không phải penetration test.
> Không tuyên bố hệ thống an toàn — chỉ liệt kê cơ chế nhận diện được và vùng chưa xác minh.

## Cơ chế bảo mật nhận diện được

| Cơ chế | Trạng thái | Evidence |
|---|---|---|
| Không bake secret vào image | `[VERIFIED]` | `Dockerfile` chỉ COPY package dir + config; comment L34-36 nêu rõ |
| Secret tách khỏi ConfigMap | `[VERIFIED]` | `configmap.yaml` chỉ chứa HMIP_ENV/HMIP_LOG_LEVEL; `job.yaml` L18-19 để sẵn `secretRef` dạng comment |
| Không có data runtime trong image | `[VERIFIED]` | `data/`, `reports/`, `knowledge/dynamic/` không được COPY |
| Config bất biến sau freeze | `[VERIFIED]` | `FrozenConfig` dùng `MappingProxyType` + deepcopy (`config.py` L38) |
| Registry bất biến khi chạy | `[VERIFIED]` | `register()` chỉ cho phép ở state READY (`registry.py` L69-75) |
| Validate đầu vào bằng JSON Schema | `[VERIFIED]` | task `validate` dùng `jsonschema` với `schemas/schema.json` |
| Validate ontology + referential integrity | `[VERIFIED]` | `loader.py:load_dataset` L107-145 |
| Không `eval`/`exec`/`shell=True` | `[VERIFIED]` | grep 0 kết quả |
| YAML an toàn | `[VERIFIED]` | dùng `yaml.safe_load` ở cả 3 nơi (`config.py`, `workflow.py`, `workflow_engine.py`) |

## Vùng KHÔNG có / KHÔNG xác minh được

| Vùng | Trạng thái |
|---|---|
| Authentication | **Không tồn tại** — không có bề mặt mạng nào cần xác thực |
| Authorization | **Không tồn tại** |
| Session / JWT / OAuth | **Không tồn tại** |
| Network boundary | **Không có** — không mở port, không gọi ra ngoài `[VERIFIED]` |
| Secret management | **Stub** — `_resolve_secrets()` là pass-through (`config.py` L166-168) |
| File upload | Không tồn tại |
| Command execution | Không tồn tại |
| Database access control | Không áp dụng (không có DB) |

## Rủi ro đã nhận diện

### R-01 — `redact_fields` là cảm giác an toàn giả  `[VERIFIED]`

`config/logging.yaml` khai báo redact cho `password`, `token`, `secret`, `api_key`. **Không có logic redact nào tồn tại** trong `core/observability.py`. Người vận hành đọc file config có thể tin rằng log đang được lọc secret — thực tế không.

Khuyến nghị: hiện thực redaction processor trong structlog pipeline, hoặc xoá khai báo.

### R-02 — Lineage ghi nguyên vẹn input/output ra file  `[VERIFIED]`

`PersistentLineageTracer.record_trace` (`lineage.py` L131-152) serialize toàn bộ `input_val`/`output_val` ra `lineage.jsonl` **không lọc gì**. Với PRC-001 hiện tại payload chỉ là dữ liệu giá công khai nên vô hại. Nhưng nếu về sau có task xử lý credential hoặc PII, chúng sẽ nằm nguyên văn trong file lineage.

### R-03 — Marker readiness không bao giờ được xoá  `[VERIFIED]`

`clear_ready()` tồn tại nhưng không được gọi ở đâu (`readiness.py` L57-65, docstring tự thừa nhận). Nếu `HMIP_READY_FILE` trỏ vào volume bền vững, một lần bootstrap thành công sẽ khiến readiness check **luôn trả READY** mãi mãi, kể cả sau khi bootstrap lần sau thất bại. Với `emptyDir` hiện tại thì rủi ro này không phát sinh.

### R-04 — Config không được validate theo schema  `[VERIFIED]`

`ConfigLoader.validate()` chỉ kiểm tra kiểu dict (`config.py` L96-100). Config sai/độc hại về mặt nội dung sẽ đi lọt.

## Không được xác minh

- Chưa chạy dependency vulnerability scan (`pip-audit`/`safety`) — nằm ngoài phạm vi discovery source-based.
- Chưa đánh giá tư thế bảo mật của image `python:3.12-slim`.
