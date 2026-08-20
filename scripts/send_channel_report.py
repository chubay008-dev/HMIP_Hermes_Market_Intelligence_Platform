"""Gửi báo cáo Channel Comparison 13 kênh qua Telegram + Discord + Gmail.
Chạy bởi cron (2 lần/ngày). Đọc prices_real.json, tính giá TB từng kênh, gửi."""
import json, os, subprocess, sys
from pathlib import Path

REPO = Path("/home/kali/Projects/HMIP/repo")
prices = json.load(open(REPO / "knowledge" / "master" / "prices_real.json", encoding="utf-8"))

WANT = ["tiki", "lotte", "bachhoaxanh", "emart", "winmart", "winmart_plus",
        "coopmart", "aeon", "go", "mmmega", "circlek", "gs25", "seveneleven",
        "shopee", "lazada", "tiktok", "websosanh"]
LABEL = {"tiki": "Tiki", "lotte": "LotteMart", "bachhoaxanh": "BachHoaXanh", "emart": "Emart",
         "winmart": "WinMart", "winmart_plus": "WinMart+", "coopmart": "Co.opmart", "aeon": "AEON",
         "go": "GO!", "mmmega": "MM Mega Market", "circlek": "Circle K", "gs25": "GS25",
         "seveneleven": "7-Eleven", "shopee": "Shopee", "lazada": "Lazada", "tiktok": "TikTok Shop",
         "websosanh": "websosanh"}

stat = {}
for p in prices["prices"]:
    for k, v in (p.get("channels") or {}).items():
        if k in WANT and v.get("case_vnd"):
            if k not in stat:
                stat[k] = [0, 0]
            stat[k][0] += v["case_vnd"]
            stat[k][1] += 1

avgs = {k: stat[k][0] // stat[k][1] for k in stat}
min_avg = min(avgs.values())
rows = sorted(avgs.items(), key=lambda x: x[1])
lines = [f"• {LABEL[k]:13} TB={v:,}₫  Index={v / min_avg * 100:.1f}  N={stat[k][1]}" for k, v in rows]
body = "\n".join(lines)

# mẫu 3 SKU nhiều kênh nhất
samp = sorted(prices["prices"], key=lambda p: len(p.get("channels", {})), reverse=True)[:3]
samp_lines = []
for p in samp:
    ch = p.get("channels", {})
    pp = ", ".join(f"{LABEL.get(k, k)}:{v['case_vnd']:,}₫" for k, v in ch.items() if v.get("case_vnd"))
    best = p.get("best_case_vnd") or p.get("price_case_vnd") or 0
    bch = LABEL.get(p.get("best_channel") or p.get("source"), "?")
    samp_lines.append(f"  - {p['name']} → rẻ nhất {bch} ({best:,}₫)\n    {pp}")

MSG = (f"📊 *HMIP Channel Comparison — 13 kênh bán lẻ VN*\n"
       f"🗓 Cập nhật: {prices['meta'].get('captured_date')}\n"
       f"🍺 72 SKU • Giá TB thùng 24 lon theo kênh (Index: rẻ nhất=100):\n\n"
       f"{body}\n\n"
       f"_Mẫu SKU (giá từng kênh):_\n" + "\n".join(samp_lines) +
       f"\n\n▶ Chi tiết: https://hmip.onrender.com/workspace (section Channel Comparison)")

HERMES_BIN = "/home/kali/.local/bin/hermes"  # absolute: cron PATH lacks ~/.local/bin
DRY = os.environ.get("DRY_RUN")

def _send(args, label, timeout=30):
    if DRY:
        print(f"[{label}] DRY_RUN — would deliver {len(MSG)} chars to {args[args.index('--to')+1] if '--to' in args else 'gmail'}")
        return
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    print(f"{label}:", (r.stdout.strip() or r.stderr.strip())[:160])

# Telegram
_send([HERMES_BIN, "send", "--to", "telegram:8891619372", MSG], "TG")
# Discord
_send([HERMES_BIN, "send", "--to", "discord:1533881868678725696", MSG], "Discord")
# Gmail
GB = MSG.replace("*", "").replace("_", "")
_send(["/home/kali/.hermes/.gw-venv/bin/python",
       "/home/kali/.hermes/skills/productivity/google-workspace/scripts/google_api.py",
       "gmail", "send", "--to", "chubay008@gmail.com",
       "--subject", "HMIP Channel Comparison - 13 kenh ban le VN (gia that)",
       "--body", GB], "Gmail", timeout=60)
