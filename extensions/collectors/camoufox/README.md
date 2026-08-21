# Camoufox Beer-Price Collector (VN)

Bộ thu thập giá bia từ 4 trang bán bia VN dùng **Camoufox** (Firefox chống-detect),
thay thế các collector dùng API/thuê proxy. Khớp hướng "collector giá thật đa kênh"
của HMIP, nhưng chạy độc lập (không phụ thuộc `extensions/pi`).

## Tại sao Camoufox?
- Các site VN (khotangbiabi, beerhouse, bianhagau, vietgourmet) dùng WAF /
  lazy-load JS → Chromium thường và API public dễ bị block.
- Camoufox = Firefox đã patch fingerprint → qua được bài test chống-bot
  (WebDriver = missing), random OS mỗi lần chạy.

## Cấu trúc file
| File | Vai trò |
|---|---|
| `camoufox_scraper.py` | Helper quét: `scrape`, `scrape_sync`, `scrape_many`, `scrape_age_gate` (xử lý cửa xác nhận tuổi 18+) |
| `bia_parsers.py` | Parser tách TÊN + GIÁ từ HTML của 4 site (mỗi site 1 hàm riêng) |
| `bia_monitor.py` | Hệ thống giám sát: quét 4 site → lưu SQLite `bia_prices.db` |
| `run_bia_monitor.sh` | Wrapper chạy bởi cron (deliver=local, không gửi Telegram/Discord) |

## Cài đặt
```bash
python3 -m venv camoufox-venv
source camoufox-venv/bin/activate
pip install camoufox
python -m camoufox fetch        # tải Firefox build (~660MB)
```

## Chạy
```bash
source camoufox-venv/bin/activate
python bia_monitor.py            # quét + lưu DB
python bia_monitor.py --report   # in giá hôm nay
python bia_monitor.py --changes  # sản phẩm tăng/giảm giá
```

## Cấu trúc DB (`bia_prices.db`)
- `products(site, sku_key, name, url)` — UNIQUE(site, sku_key)
- `price_history(product_id, price, currency, scraped_at)` — 1 dòng/ngày/sản phẩm

## Site đã hỗ trợ + cách parse
- **bianhagau.vn / vietgourmet.vn**: WooCommerce (`woocommerce-loop-product__title` + `woocommerce-Price-amount`)
- **beerhouse.vn**: KiotViet (`.product-title` + `.new-price` dạng `695.000đ`)
- **khotangbiabi.vn**: theme riêng, tên nằm trong slug URL sản phẩm
- **vietgourmet.vn**: có cửa xác nhận tuổi → `scrape_age_gate` click `.age-gate-submit-yes`

## Lưu ý
- `bia_prices.db` là dữ liệu (không commit vào git — xem `.gitignore`).
- beerhouse / khotangbiabi nhiều mục để "Giá liên hệ" (price=None) do lazy-load.
- Chạy headless trên server không màn hình: `AsyncCamoufox(headless=True)`.
