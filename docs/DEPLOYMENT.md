# DEPLOYMENT — HMIP

## Mô hình thực thi

`[VERIFIED]` **Run-to-completion CLI**, không phải long-running server. Điều này chi phối mọi quyết định deploy bên dưới.

## Local development

```bash
python3 -m venv .venv-local          # KHÔNG dùng .venv trong repo (là venv Windows)
.venv-local/bin/pip install -e ".[dev]"
.venv-local/bin/python -m platform_.bootstrap
```

## Docker

`Dockerfile` — `[VERIFIED]`:

| Khía cạnh | Giá trị |
|---|---|
| Base image | `python:3.12-slim` |
| Package manager | `uv` (`uv pip install --system .`) |
| COPY | `pyproject.toml`, `core`, `domains`, `knowledge`, `platform_`, `shared`, `config` |
| **KHÔNG** COPY | `data/`, `reports/`, `knowledge/dynamic/`, secret |
| ENV | `HMIP_ENV=production`, `PYTHONUNBUFFERED=1` |
| HEALTHCHECK | `python -m platform_.health`, 30s/5s/start 5s/retries 3 |
| ENTRYPOINT | `python -m platform_.bootstrap` |

Ghi chú layer caching: dependency install **không tách được** khỏi source copy, vì `[tool.setuptools.packages.find]` cần package dir có mặt lúc install. Đánh đổi có chủ ý, ghi rõ trong comment Dockerfile.

## Docker Compose

`deployment/docker-compose.yml`: 1 service `hmip-bootstrap`, **không expose port** (đúng với mô hình CLI).

Volume (bind mount thật — dữ liệu bền vững):
- `./volumes/reports:/app/reports`
- `./volumes/data:/app/data`
- `./volumes/knowledge-dynamic:/app/knowledge/dynamic`

## Kubernetes

`deployment/kubernetes/job.yaml` — `batch/v1 Job`, **không phải Deployment**:

```text
Job (backoffLimit 2, restartPolicy Never)
   ↓
Pod  ← envFrom ConfigMap hmip-config
   ↓
container hmip:latest
   requests: cpu 250m / mem 256Mi
   limits:   cpu 1    / mem 512Mi
   volumeMounts: /app/reports, /app/data, /app/knowledge/dynamic  (emptyDir)
```

Không có `livenessProbe`/`readinessProbe` — có chủ ý: với Job, việc job thành công/thất bại **chính là** tín hiệu readiness. Comment trong file nêu rõ.

⚠️ **`emptyDir` khiến report và lineage mất khi pod kết thúc** — khác hẳn compose (bind mount bền vững). Xem F-03.

Chạy định kỳ (ví dụ PRC-001 hàng ngày): cần bọc thành `CronJob` — comment gợi ý nhưng **manifest chưa tồn tại** trong repo.

## Health / Readiness

| Loại | Cơ chế | Kiểm gì |
|---|---|---|
| Liveness | exit code của `python -m platform_.health` | Python >= 3.12 (chỉ vậy) |
| Readiness | exit code của `python -m platform_.readiness` | marker file `HMIP_READY_FILE` tồn tại |

Đây là **exec check, không phải HTTP endpoint** — đúng cho mô hình batch. Docstring trong `health.py`/`readiness.py` ghi rõ: nếu sau này có service chạy dài, cần chuyển thành HTTP endpoint thật.

## Cạm bẫy khi deploy

1. Container **chỉ chạy bootstrap** — không thực thi WF-PRC-001 (F-01).
2. `HMIP_LOG_LEVEL` đặt trong ConfigMap **không có tác dụng** (F-04).
3. Marker readiness không bao giờ được xoá; an toàn với `emptyDir`, rủi ro nếu mount volume bền vững (R-03).
