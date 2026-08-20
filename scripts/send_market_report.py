"""Gửi báo cáo Thị trường Bia VN (thị phần + xu hướng) qua Telegram + Discord + Gmail.
Chạy bởi cron. Đọc knowledge/master/market_share.json + trends.json."""
import json, subprocess
from pathlib import Path

REPO = Path("/home/kali/Projects/HMIP/repo")
share = json.load(open(REPO / "knowledge" / "master" / "market_share.json", encoding="utf-8"))
trends = json.load(open(REPO / "knowledge" / "master" / "trends.json", encoding="utf-8"))

by_brand = share.get("by_brand", [])
by_seg = share.get("by_segment", [])
facts = share.get("key_facts", [])
tr = trends.get("trends", [])

brand_lines = "\n".join(f"• {b['brand']}: {b['share_pct']}% ({b['country']})" for b in by_brand if b.get("share_pct"))
seg_lines = "\n".join(f"• {s['segment'].split(' (')[0]}: {s['share_pct']}%" for s in by_seg)
trend_lines = "\n".join(f"🔥 {t['name']}" + (f" (CAGR {t['cagr_pct']}%)" if t.get("cagr_pct") else "") for t in tr)
fact_lines = "\n".join(f"• {f}" for f in facts)

MSG = (f"📈 *HMIP — Thị trường Bia Việt Nam*\n"
       f"🗓 Cập nhật: {share.get('meta',{}).get('captured_date')}\n\n"
       f"*Thị phần theo thương hiệu:*\n{brand_lines}\n\n"
       f"*Phân khúc:*\n{seg_lines}\n\n"
       f"*Xu hướng bia mới:*\n{trend_lines}\n\n"
       f"*Điểm chính:*\n{fact_lines}\n\n"
       f"▶ Chi tiết: https://hmip.onrender.com/workspace (section Thị trường Bia VN)")

r1 = subprocess.run(["/home/kali/.local/bin/hermes", "send", "--to", "telegram:8891619372", MSG],
                    capture_output=True, text=True, timeout=30)
print("TG:", r1.stdout.strip() or r1.stderr.strip())
r2 = subprocess.run(["/home/kali/.local/bin/hermes", "send", "--to", "discord:1533881868678725696", MSG],
                    capture_output=True, text=True, timeout=30)
print("Discord:", r2.stdout.strip() or r2.stderr.strip())
GB = MSG.replace("*", "").replace("_", "")
r3 = subprocess.run(["/home/kali/.hermes/.gw-venv/bin/python",
                     "/home/kali/.hermes/skills/productivity/google-workspace/scripts/google_api.py",
                     "gmail", "send", "--to", "chubay008@gmail.com",
                     "--subject", "HMIP Thi truong Bia VN - thi phan & xu huong",
                     "--body", GB], capture_output=True, text=True, timeout=60)
print("Gmail:", r3.stdout.strip()[:120] or r3.stderr.strip()[:120])
