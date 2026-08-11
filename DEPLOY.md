# Triển khai HMIP lên Cloud

Hướng dẫn đưa HMIP từ local lên internet, mở bằng web từ mọi nơi.

## Tóm tắt các bước

1. Build image (đã có `Dockerfile`)
2. Đẩy lên registry (Docker Hub / GitHub Container Registry)
3. Tạo service trên host miễn phí (Render / Fly.io / Railway)
4. Set env: `HMIP_API_TOKEN` (bắt buộc) + Telegram (tuỳ chọn)
5. Mở web, nhập token

## 1. Build & test local

```bash
docker compose up --build
# mở http://localhost:8000
# nhập token: changeme-in-production (đổi trong .env)
```

Test auth:
```bash
curl http://localhost:8000/api/latest          # 401
curl -H "Authorization: Bearer changeme-in-production" \
     http://localhost:8000/api/latest          # 200
```

## 2. Đẩy lên registry

**Docker Hub:**
```bash
docker tag hmip:test <your-user>/hmip:latest
docker push <your-user>/hmip:latest
```

**GitHub Container Registry:**
```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u <user> --password-stdin
docker tag hmip:test ghcr.io/<user>/hmip:latest
docker push ghcr.io/<user>/hmip:latest
```

## 3. Deploy lên host miễn phí

### Render (đơn giản nhất)

1. https://render.com → New → Web Service
2. Connect repo GitHub chứa HMIP
3. Runtime: Docker; Branch: main
4. Env vars:
   - `HMIP_API_TOKEN` = `<chuỗi dài ngẫu nhiên>`
   - `HMIP_AUTOSCAN` = `on`
   - `HMIP_SCAN_INTERVAL_MIN` = `30`
   - `HMIP_COLLECT_MODE` = `demo` (hoặc `http` nếu có API thật)
   - `HMIP_TELEGRAM_BOT_TOKEN`, `HMIP_TELEGRAM_CHAT_ID` (tùy chọn)
5. Deploy → Render cho URL `https://hmip-xxx.onrender.com`

Free tier: sau 15 phút không truy cập sẽ "sleep". Auto-scan vẫn chạy
nhưng bị gián đoạn. Để luôn thức, dùng Fly.io hoặc Railway.

### Fly.io (luôn thức, có 3 VM free)

```bash
fly launch --image <your-user>/hmip:latest
fly secrets set HMIP_API_TOKEN=<token> HMIP_AUTOSCAN=on
fly deploy
fly open
```

### Railway

1. https://railway.app → New Project → Deploy from GitHub repo
2. Railway tự detect Dockerfile
3. Tab Variables: set `HMIP_API_TOKEN` etc.
4. Deploy → có URL công khai

## 4. Bật xác thực (BẮT BUỘC khi mở internet)

App dùng Bearer token (`HMIP_API_TOKEN`). Khi deploy, set biến này
thành chuỗi dài ngẫu nhiên. Mọi API (trừ `/api/health` và dashboard
shell `/`) yêu cầu header:

```
Authorization: Bearer <HMIP_API_TOKEN>
```

Dashboard web có form login nhập token, lưu trong localStorage.

Dev local (không set `HMIP_API_TOKEN`) → auth tự tắt, truy cập tự do.

**Đừng commit token vào repo.** Dùng env / secret của host.


## 5. Bật cảnh báo Telegram

1. Chat với @BotFather → /newbot → lấy token
2. Chat với @userinfobot → lấy chat_id
3. Set `HMIP_TELEGRAM_BOT_TOKEN` + `HMIP_TELEGRAM_CHAT_ID`
4. Khi giá vượt ngưỡng → nhận tin nhắn tự động

## Lưu ý bảo mật

- **BẮT BUỘC đổi `HMIP_API_TOKEN`** thành chuỗi dài ngẫu nhiên. Mặc định
  `changeme-in-production` chỉ dùng test.
- Không commit token vào repo. Dùng env / secret của host.
- Đóng `/docs` khi production nếu không muốn lộ schema (xóa khỏi
  `_EXEMPT_PREFIXES` trong `extensions/auth.py`).
- SQLite gắn volume — host restart không mất dữ liệu. Muốn scale nhiều
  replica cần chuyển sang Postgres (sửa `extensions/db.py`).

## Chuyển sang nguồn giá thật

Đổi `HMIP_COLLECT_MODE=http` + `HMIP_PRICE_API_BASE=<url>` (xem
APP_README.md mục "Nối nguồn giá thật").
