# CODEBASE_INVENTORY — HMIP

> Phase 1 output. Mô tả **những gì tồn tại**, chưa kết luận kiến trúc.
> Mọi dòng dưới đây được xác nhận bằng `find`/`wc -l`/đọc file trực tiếp.

## 1. Repository overview

| Thuộc tính | Giá trị | Evidence |
|---|---|---|
| Tên package | `hmip` v0.1.0 | `pyproject.toml` L2-3 |
| Ngôn ngữ | Python, `requires-python = ">=3.12"` | `pyproject.toml` L5 |
| Runtime deps | `pyyaml`, `structlog`, `jsonschema` (3 gói) | `pyproject.toml` L6-10 |
| Dev deps | `pytest`, `pytest-cov`, `ruff`, `mypy` | `pyproject.toml` L13-18 |
| Tổng file `.py` | 77 | `find -name '*.py' \| wc -l` |
| Tổng LOC (py+yaml+json+toml) | ~7.449 | `wc -l` trên toàn bộ file nguồn |
| Số file `.md` | 34 (spec pack 01-20 + sprint status) | `find -name '*.md'` |
| Database | **Không có** — không có ORM, driver, migration nào | `[VERIFIED]` grep toàn repo: 0 kết quả cho sqlalchemy/psycopg/sqlite3 |
| HTTP server | **Không có** — không có FastAPI/Flask/uvicorn | `[VERIFIED]` không có trong dependencies |

## 2. Directory tree (bỏ `.venv`, cache)

```text
.
├── core/                  # runtime kernel (11 module .py)
├── platform_/             # CLI entrypoints (bootstrap/health/readiness/diagnostics)
├── domains/beer/pricing/  # domain vertical slice PRC-001
│   ├── skills/            # 6 task handler
│   ├── workflows/         # WF-PRC-001.yaml
│   ├── schemas/           # schema.json
│   ├── prompts/           # extract_price.md
│   └── tests/             # 4 test file cấp domain
├── knowledge/
│   ├── ontology/          # loader.py, models.py, core_schema.json
│   ├── master/            # brands/products/skus.json (master data)
│   └── dynamic/           # rỗng (.gitkeep) — đích ghi lineage.jsonl
├── shared/                # constants.py, types.py
├── config/                # runtime/logging/deployment .yaml
├── deployment/            # docker-compose.yml + kubernetes/{configmap,job}.yaml
├── data/{raw,normalized,processed,validated}/   # tất cả đều RỖNG (.gitkeep)
├── reports/               # rỗng (.gitkeep) — đích ghi BootstrapReport JSON
├── playbooks/             # rỗng (.gitkeep)
└── tests/{unit,integration,workflow,chaos,prompt}/
```

## 3. Entry points  `[VERIFIED]`

Cả 3 đều là **CLI run-to-completion**, không phải server. Mỗi file có `main() -> int` + `if __name__ == "__main__": raise SystemExit(main())`.

| Entry point | File | Chức năng | Exit code |
|---|---|---|---|
| `python -m platform_.bootstrap` | `platform_/bootstrap.py:main` | Chạy 8 bước bootstrap, ghi report JSON, `mark_ready()` | 0 OK / 1 fail |
| `python -m platform_.health` | `platform_/health.py:main` | Liveness (kiểm tra Python >= 3.12) | 0 HEALTHY / 1 |
| `python -m platform_.readiness` | `platform_/readiness.py:main` | Kiểm tra marker file tồn tại | 0 READY / 1 |

**Không có entry point nào thực thi workflow.** Xem `VERIFICATION_REPORT.md` finding F-01.

## 4. Configuration files

| File | Nội dung chính | Consumer |
|---|---|---|
| `config/runtime.yaml` | `runtime.environment`, `registry.freeze_on_bootstrap`, `policy.config_mode` | `core.config.ConfigLoader` |
| `config/logging.yaml` | `logging.level/format/redact_fields` | (nạp vào config, xem F-04) |
| `config/deployment.yaml` | container/health_check/readiness/resources | (nạp vào config, xem F-04) |
| `.env.example` | 9 biến `HMIP_*` có chú thích | tài liệu tham chiếu |

## 5. Deployment files

- `Dockerfile` — base `python:3.12-slim`, cài bằng `uv`, `HEALTHCHECK CMD python -m platform_.health`, `ENTRYPOINT python -m platform_.bootstrap`.
- `deployment/docker-compose.yml` — 1 service `hmip-bootstrap`, không expose port, 3 volume.
- `deployment/kubernetes/job.yaml` — `batch/v1 Job` (không phải Deployment), `backoffLimit: 2`, `restartPolicy: Never`.
- `deployment/kubernetes/configmap.yaml` — chỉ `HMIP_ENV`, `HMIP_LOG_LEVEL` (không secret).

## 6. Test structure  `[VERIFIED]` — đã chạy thật

```text
tests/unit/         14 file — core kernel
tests/workflow/      3 file — PRC-001 e2e / compensation / regression
tests/chaos/         5 file — deadlock, dependency_unavailable, disk_full, network_timeout, storage_failure
tests/integration/   1 file + fixture yaml
tests/prompt/        2 file + 2 golden JSON
domains/.../tests/   4 file
```

Kết quả chạy thực tế: **268 passed, coverage 94.07%** (gate `--cov-fail-under=80` trong `pyproject.toml` L60).

## 7. External integrations

**Không có integration ngoài nào.** `[VERIFIED]` — 0 HTTP client, 0 SDK, 0 message queue trong dependencies.
`CollectPriceAdapter` là mock in-memory với dict `_MOCK_SOURCE_DATA` chứa đúng **1 bản ghi** (`("P123","shopee")`), `collect_price.py` L25-35.

## 8. Vùng không kiểm tra được / bất thường

- `.venv/` trong repo là **virtualenv Windows** (`.venv/Scripts/*.exe`, không có `.venv/bin/`) → không chạy được trên máy Linux này. Đã tạo venv riêng ở `/tmp/hmip-venv` để verify, **không đụng vào repo**.
- `data/*`, `reports/`, `playbooks/`, `knowledge/dynamic/` đều rỗng (chỉ `.gitkeep`) — chưa từng có run nào để lại artifact trong repo.
- `.coverage` (114KB) là build artifact bị commit vào repo.
