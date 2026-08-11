# CONFIGURATION — HMIP

> Không có giá trị secret nào trong tài liệu này (mục 9 của workflow).

## Biến môi trường

| Variable | Purpose | Required | Đọc bởi | Có hiệu lực? |
|---|---|:---:|---|---|
| `HMIP_ENV` | Tên môi trường (development/staging/production) | Không | `config/*.yaml` qua `${HMIP_ENV:-...}` | Có `[VERIFIED]` |
| `HMIP_RUNTIME_VERSION` | Ghi đè runtime_version trong BootstrapReport | Không | `core/models.py` L25-31 | Có `[VERIFIED]` |
| `HMIP_KERNEL_VERSION` | Ghi đè kernel_version | Không | `core/models.py` L34-36 | Có `[VERIFIED]` |
| `HMIP_LOG_LEVEL` | Mức log | Không | chỉ được expand vào `config/logging.yaml` | **KHÔNG** — xem F-04 |
| `HMIP_SECRET_PROVIDER` | Chọn secret provider | Không | — | **KHÔNG** — stub `[VERIFIED]` |
| `HMIP_CONFIG_PATH` | Thư mục chứa config/*.yaml (mặc định `./config`) | Không | `platform_/bootstrap.py` L47-52 | Có `[VERIFIED]` |
| `HMIP_DATA_DIR` | Thư mục data pipeline | Không | — | **KHÔNG** — F-06 |
| `HMIP_REPORT_DIR` | Nơi ghi BootstrapReport (mặc định `./reports`) | Không | `platform_/bootstrap.py` L68-70 | Có `[VERIFIED]` |
| `HMIP_READY_FILE` | Đường dẫn marker readiness (mặc định temp dir) | Không | `platform_/readiness.py` L31-37 | Có `[VERIFIED]` |

Không biến nào bắt buộc — mọi biến đều có fallback. `[VERIFIED]`

## Cú pháp expand

`core/config.py` L29: `${VAR}` và `${VAR:-default}`.
`${VAR}` không có default mà biến không tồn tại → raise `ConfigValidationException` code `CONFIG_UNRESOLVED_VARIABLE` (L155-158).

## Thứ tự nạp config

`platform_/bootstrap.py` L42: `runtime.yaml → logging.yaml → deployment.yaml`, deep-merge theo thứ tự (file sau ghi đè file trước ở khoá trùng). Sau merge → expand → resolve secrets (stub) → validate → freeze + fingerprint SHA256.

## Khoá config được khai báo nhưng chưa được đọc  `[VERIFIED]` — F-04

`logging.level`, `logging.format`, `logging.redact_fields`, `registry.freeze_on_bootstrap`, `policy.config_mode`, `container.*`, `health_check.*`, `readiness_check.*`, `resources.*`.

Chúng nằm trong `FrozenConfig` nhưng không code nào truy vấn. Giá trị hiện tại mang tính tài liệu/tham chiếu cho deployment manifest, không điều khiển hành vi runtime.
