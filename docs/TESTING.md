# TESTING — HMIP

## Kết quả chạy thật  `[VERIFIED]`

```
268 passed in 3.24s
Required test coverage of 80% reached. Total coverage: 94.07%
```

Lệnh: `pytest -q` (venv sạch `/tmp/hmip-venv`, vì `.venv` trong repo là virtualenv Windows không chạy được trên Linux).

## Framework & cấu hình

`pyproject.toml` L53-74: pytest + pytest-cov, `testpaths = ["tests", "domains"]`, `--cov-fail-under=80`, `branch = true`.

## Cấu trúc

| Tầng | Số file | Nội dung |
|---|---:|---|
| `tests/unit/` | 14 | từng module core độc lập |
| `tests/workflow/` | 3 | PRC-001 end-to-end, compensation, regression |
| `tests/chaos/` | 5 | deadlock, dependency_unavailable, disk_full, network_timeout, storage_failure |
| `tests/integration/` | 1 | workflow execution flow + fixture YAML |
| `tests/prompt/` | 2 | golden-file test cho extract & decision |
| `domains/.../tests/` | 4 | decision engine, enrich, models, skills |

Có chaos test và golden-file test — vượt mức thường thấy ở dự án giai đoạn này.

## Coverage theo module

| Module | Coverage |
|---|---:|
| `core/models.py`, `observability.py`, `planner.py`, `registry.py` | 100% |
| `core/workflow_engine.py` | 92% |
| `core/workflow.py` | 91% |
| `knowledge/ontology/loader.py` | 89% |
| `knowledge/ontology/models.py` | 88% |
| `platform_/health.py` | 83% |
| `shared/types.py` | 0% (chỉ type alias, không có runtime code) |
| **TOTAL** | **94.07%** |

## Phân biệt "có test" vs "được test đầy đủ"

Theo mục 21 của workflow — hai điều này khác nhau:

| Vùng | Có test | Được test đầy đủ? |
|---|:---:|---|
| Core kernel | ✅ | ✅ 100% nhiều module, có chaos test |
| PRC-001 happy path | ✅ | ✅ end-to-end + regression + golden |
| Compensation | ✅ | ⚠️ Cơ chế được test kỹ, nhưng **mọi rollback đều no-op** — chưa từng test rollback có side effect thật (F-07) |
| Adapter thật (HTTP/scraping) | ❌ | Không tồn tại để test |
| LLM extraction | ❌ | Chưa có hạ tầng LLM; extract là parser tất định |
| Config schema validation | ⚠️ | `validate()` chỉ check kiểu dict — test chỉ xác nhận hành vi hiện tại, không xác nhận tính đúng đắn (F-05) |
| Logging redaction | ❌ | Không có logic để test (R-01) |
| Container/K8s deploy | ❌ | Không có test cho Dockerfile/manifest |

## Cạm bẫy môi trường

`.venv/` trong repo chỉ có `Scripts/*.exe` (Windows). Trên Linux/macOS phải tạo venv mới:

```bash
python3 -m venv /tmp/hmip-venv
/tmp/hmip-venv/bin/pip install -e ".[dev]"
/tmp/hmip-venv/bin/python -m pytest -q
```
