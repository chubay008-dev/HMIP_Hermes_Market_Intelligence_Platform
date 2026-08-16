# Hướng dẫn setup Supabase (PostgreSQL) cho HMIP

> Giải quyết vấn đề **Render free tier ephemeral disk** — mỗi deploy/restart
> xoá SQLite → mất dữ liệu giá đã seed/collect. PostgreSQL (Supabase free
> 500MB) lưu dữ liệu bền vững qua deploy.

## Bước 1: Tạo Supabase project (5 phút, free)

1. Vào https://supabase.com → **Sign up** (GitHub/Google) → **New project**
2. Đặt tên: `hmip` (hoặc tùy ý), region: **Southeast Asia (Singapore)**
3. Tạo password mạnh → **lưu lại** (chỉ hiện 1 lần)
4. Đợi ~2 phút project khởi tạo

## Bước 2: Lấy connection string

1. Supabase Dashboard → **Project Settings** (⚙️) → **Database**
2. Mục **Connection string** → chọn **URI** (format `postgresql://`)
3. Dạng: `postgresql://postgres.[ref]:[PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres`
4. **Thay `[PASSWORD]`** bằng password đã tạo ở Bước 1

> ⚠️ Dùng port **6543** (connection pooler, direct) — Render web service
> dùng connection ngắn, pooler phù hợp hơn port 5432 (direct).

## Bước 3: Set trên Render Dashboard

1. Render Dashboard → service **hmip** → **Environment**
2. Thêm 2 biến (đã khai báo `sync: false` trong render.yaml):

| Key | Value |
|-----|-------|
| `DATABASE_URL` | `postgresql://postgres.[ref]:[PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres` |
| `HMIP_PI_DATABASE_URL` | *(cùng giá trị trên — 2 DB dùng cùng Supabase project, bảng khác prefix)* |

3. **Save Changes** → Render tự redeploy

## Bước 4: Verify

Sau khi deploy xong (~2-3 phút), kiểm tra:

```bash
# Health (phải trả status:ok)
curl -s https://hmip.onrender.com/api/health

# Số sản phẩm (sẽ seed lại vào Postgres, ~67 SP)
curl -s https://hmip.onrender.com/api/latest | python3 -m json.tool | head

# PI status
curl -s https://hmip.onrender.com/api/price-intelligence/status
```

Sau khi **redeploy lần nữa** (push commit mới), dữ liệu **KHÔNG bị mất** —
verify bằng cách chạy lại `/api/latest` và thấy số SP không reset về 0.

## Cách hoạt động (technical)

- `extensions/db_backend.py` — abstraction layer SQLite ↔ PostgreSQL
- Khi `DATABASE_URL` set → dùng PostgreSQL (psycopg2)
- Khi không set → fallback SQLite (local dev, giữ nguyên)
- SQL conversion runtime:
  - `?` → `%s` (placeholder)
  - `INSERT OR IGNORE` → `ON CONFLICT DO NOTHING`
  - `AUTOINCREMENT` → `BIGSERIAL`
  - `PRAGMA` → skip (Postgres không cần)
- Schema tự tạo khi app khởi động (`init_db` / `init_pi_db`)
- 2 DB (products/price_points + pi_*) dùng cùng Supabase project, bảng
  khác prefix → không xung đột

## Giới hạn Supabase free

- 500MB storage (đủ cho ~500k price points, nhiều tháng)
- 7 ngày inactivity pause (Render auto-scan giữ active)
- Connection pool: 60 concurrent (đủ cho 1 web service)
