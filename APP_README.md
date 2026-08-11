# HMIP App — Hướng dẫn sử dụng thực tế

Ứng dụng web giám sát giá, chạy trên HMIP workflow kernel.

## Chạy trong 1 lệnh

```bash
./start.sh
```

Mở http://127.0.0.1:8000 — lần đầu script tự tạo virtualenv và cài dependencies (~1 phút).

| Địa chỉ | Nội dung |
|---|---|
| `/` | Dashboard giám sát giá |
| `/docs` | API docs tương tác (Swagger) |
| `/api/health` | Health check |

## Ứng dụng này làm gì

Theo dõi giá sản phẩm theo thời gian, tự động ra quyết định khi giá biến động:

| Biến động so với giá tham chiếu | Quyết định | Ý nghĩa |
|---|---|---|
| < 5% | `IGNORE` | Dao động bình thường |
| 5% – 10% | `ALERT` | Cần chú ý, báo đội giá |
| ≥ 10% | `ESCALATE` | Bất thường, báo quản lý |
| confidence < 0.7 | `HUMAN_REVIEW` | Dữ liệu không đáng tin, cần người xem |

Mỗi lần quét chạy đủ 7 bước của WF-PRC-001: `collect → extract → validate → enrich → compare → decide → alert`. Nếu bước nào lỗi, cơ chế compensation tự động rollback ngược các bước đã chạy.

## Kiến trúc

```
┌──────────────────────────────────────────────┐
│  Dashboard (extensions/web/index.html)       │
├──────────────────────────────────────────────┤
│  FastAPI (extensions/api.py)                 │  ← lớp web
├──────────────────────────────────────────────┤
│  run_workflow.py — nối engine vào runtime    │  ← fix F-01
├──────────────────────────────────────────────┤
│  HMIP core/ — KHÔNG SỬA MỘT DÒNG NÀO         │  ← kernel gốc
├──────────────────────────────────────────────┤
│  collect_adapters.py │ db.py (SQLite)        │  ← cắm vào khe có sẵn
└──────────────────────────────────────────────┘
```

Nguyên tắc: kernel HMIP là **run-to-completion**, không phải server. Lớp web **bọc bên ngoài** và gọi vào, mỗi request tạo một execution độc lập — đúng thiết kế gốc, không phá kiến trúc.

## Nối nguồn giá thật

Mặc định chạy chế độ `demo` (giá mô phỏng dao động ±12%). Để dùng API thật:

```bash
export HMIP_COLLECT_MODE=http
export HMIP_PRICE_API_BASE=https://api-cua-ban.vn/products
export HMIP_PRICE_API_KEY=<token>     # tuỳ chọn
./start.sh
```

API cần trả JSON có trường `price`. Nếu shape khác, sửa hàm `_parse_response()` trong `extensions/collect_adapters.py` — đó là điểm tuỳ biến duy nhất cần đụng tới.

## Thêm sản phẩm mới

Sản phẩm phải tồn tại trong ontology (HMIP ép kiểm tra để chống rác dữ liệu). Cần sửa 3 nơi:

1. `knowledge/master/brands.json` — thêm thương hiệu (nếu chưa có)
2. `knowledge/master/products.json` — thêm sản phẩm, trỏ `brand_id`
3. `knowledge/master/skus.json` — thêm SKU, trỏ `product_id`

Rồi thêm giá tham chiếu vào `_DEMO_CATALOG` (`extensions/collect_adapters.py`) và `_BASE_PRICES` (`extensions/run_workflow.py`).

## Cấu hình

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `HMIP_DB_PATH` | `hmip.db` | File SQLite |
| `HMIP_COLLECT_MODE` | `demo` | `demo` hoặc `http` |
| `HMIP_PRICE_API_BASE` | — | URL API giá (khi mode=http) |
| `HMIP_PRICE_API_KEY` | — | Bearer token (tuỳ chọn) |
| `HMIP_BASE_PRICE_<ID>` | — | Ghi đè giá tham chiếu 1 sản phẩm |
| `HMIP_AUTOSCAN` | `off` | `on` để bật quét tự động khi khởi động |
| `HMIP_SCAN_INTERVAL_MIN` | `30` | Chu kỳ quét (phút) |
| `HMIP_TELEGRAM_BOT_TOKEN` | — | Token bot Telegram (từ @BotFather) |
| `HMIP_TELEGRAM_CHAT_ID` | — | Chat ID nhận cảnh báo |

Ví dụ đổi giá tham chiếu của P123 thành 20.000đ:
```bash
export HMIP_BASE_PRICE_P123=20000
```

## API

```bash
# Quét 1 sản phẩm
curl -X POST localhost:8000/api/run \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"P123","source":"shopee"}'

# Quét tất cả
curl -X POST localhost:8000/api/run-all

# Giá mới nhất
curl localhost:8000/api/latest

# Lịch sử 1 sản phẩm
curl localhost:8000/api/history/P123

# Danh sách cảnh báo
curl localhost:8000/api/alerts
```

## Tự động hóa & cảnh báo đẩy

### Quét định kỳ (auto-scan)

Bật quét tự động nền qua API hoặc env:

```bash
# Cách 1: qua API (từ dashboard bấm nút "Tự động")
curl -X POST localhost:8000/api/autoscan/start
curl -X POST localhost:8000/api/autoscan/stop
curl localhost:8000/api/autoscan/status

# Cách 2: bật sẵn khi khởi động
export HMIP_AUTOSCAN=on
export HMIP_SCAN_INTERVAL_MIN=30   # chu kỳ (phút)
./start.sh
```

Mỗi chu kỳ quét toàn bộ catalog, ghi SQLite, và đẩy cảnh báo nếu quyết định ≠ IGNORE.

### Cảnh báo Telegram

Khi một sản phẩm vượt ngưỡng, hệ thống gửi tin nhắn Telegram:

```bash
export HMIP_TELEGRAM_BOT_TOKEN=<token từ @BotFather>
export HMIP_TELEGRAM_CHAT_ID=<chat_id của bạn>
```

Nếu chưa cấu hình, cảnh báo tự động chuyển sang **ghi log** (console fallback) — app vẫn chạy, không lỗi.

Format tin nhắn:

```
🔴 HMIP — Cảnh báo giá
Sản phẩm: Saigon Special 330ml
Giá hiện tại: 20.083 VND
Giá tham chiếu: 18.000 VND
Biến động: ▲ +11.57%
Quyết định: ESCALATE
```

### Chạy scheduler độc lập (không cần web)

```bash
.venv-app/bin/python -m extensions.scheduler
```

Có thể chạy song song với web app — cả hai dùng chung SQLite, không xung đột.

## Test

```bash
.venv-app/bin/python -m pytest                    # 268 test gốc
.venv-app/bin/python -m pytest extensions/tests   # 16 test mới
```

## Dữ liệu lưu ở đâu

| Loại | Vị trí |
|---|---|
| Lịch sử giá | `hmip.db` (SQLite) |
| Audit trail đầy đủ | `knowledge/dynamic/lineage/lineage.jsonl` |

File lineage ghi lại **mọi bước** của mọi lần chạy kèm hash SHA256 — dùng để truy vết khi cần kiểm chứng một quyết định đã ra như thế nào.

## Giới hạn hiện tại

Nói rõ để không hiểu nhầm:

- **Chế độ `demo` sinh giá ngẫu nhiên**, không phải giá thị trường thật. Muốn dùng thật phải nối API qua `HMIP_COLLECT_MODE=http`.
- **Chưa có xác thực** — đừng mở ra internet khi chưa thêm auth.
- **Chưa có scheduler đẩy chủ động từ cloud** — auto-scan chạy trên process local; lên server cần giữ process sống (xem bước "Triển khai cloud" tiếp theo).
- **Rollback vẫn no-op** (kế thừa từ core) — vì chưa bước nào có side effect thật cần hoàn tác.
- **Telegram phải tự tạo bot** (@BotFather) — code chỉ gửi, không tạo bot.
