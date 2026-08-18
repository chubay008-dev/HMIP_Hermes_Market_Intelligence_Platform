# HMIP — Giá thật thị trường & Channel Comparison (13 kênh)

> Tóm tắt cho repo (chi tiết trong Obsidian vault:
> `BO_TRI_THUC_OBSIDIAN/HMIP_ARCHITECTURE/HMIP_REAL_PRICES_CHANNEL_COMPARISON.md`)
> Cập nhật: 2026-08-18

## Tổng quan

Hệ thống HMIP chuyển từ dữ liệu demo → **giá bia thật thị trường VN**, đa kênh,
tự động cập nhật & báo cáo.

## Nguồn dữ liệu

- `knowledge/master/prices_real.json`: 72 SKU, giá thùng 24 + lẻ 1, source + confidence.
- `knowledge/master/brands.json` (40), `products.json` (72), `skus.json` (72): catalog thực tế.
- `knowledge/dynamic/news.json`: 20 tin tức thật (thuế TTĐB bia 2026–2027).

## 13 kênh bán lẻ VN (đầy đủ)

Tiki, LotteMart, Bách Hóa Xanh, Emart, WinMart, WinMart+, Co.opmart, AEON, GO!,
MM Mega Market, Circle K, GS25, 7-Eleven, Shopee, Lazada, TikTok Shop, websosanh.

Mỗi SKU có trường `channels: {kênh: {case_vnd, single_vnd, confidence}}` + `best_channel`.

## Code liên quan

- `extensions/pi/real_prices.py` — loader + `get_channel_comparison()`
- `extensions/api.py` — `/api/prices-real`, `/api/prices-real/channels`
- `extensions/web/index.html` — tab Giám sát (giá thật)
- `extensions/web/pi.html` — tab Workspace (Channel Comparison: bảng + chart + filter)
- `scripts/auto_update.py` — pipeline tự động
- `scripts/send_channel_report.py` — báo cáo Channel Comparison (TG+Discord+Gmail)

## Tự động hóa (Cron Hermes)

| Job | Lịch | Việc |
|-----|------|------|
| `2857cda84856` | 30p | Fast Tiki (7 SKU) |
| `3daed9003a5d` | 3h | Deep DuckDuckGo (65 SKU) |
| `d9dc4df23183` | 8h & 20h/ngày | Báo cáo Channel Comparison 13 kênh (TG+Discord+Gmail) |

## Biến động giá

Giá bia niêm yết ổn định theo tháng; biến động từ promotion + thuế TTĐB.
Gửi báo cáo 2 lần/ngày là đủ.

## Pitfalls

- `core_schema.json` `additionalProperties:false` → không sửa master catalog; giá thật lưu riêng.
- Tiki rate-limit, DuckDuckGo block → deep scan đôi khi scraped=0.
- Cron `delegate_task` + hermes_tools → guardrail 50 calls → dùng script thường (DDG).
- PAT không hardcode vào repo; dùng `~/.hmip_cron_env.sh`. Revoke PAT thủ công.
