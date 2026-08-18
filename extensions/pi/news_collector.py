"""news_collector.py — Quét tin tức thật về thị trường bia VN.

Nguồn: RSS công khai của báo VN (VnExpress, CafeF, Đời sống Pháp luật...)
+ web_search fallback lọc keyword "bia / thuế TTĐB / Heineken / Sabeco / Carlsberg".
Kết quả lưu vào knowledge/dynamic/news.json (append, dedupe theo url).

Thiết kế:
- Chạy định kỳ (APScheduler) hoặc gọi thủ công collect_beer_news().
- Không scrape mạng xã hội (FB/Zalo/TikTok) làm nguồn tin chuẩn.
- Mọi item có url + title + snippet + source + fetched_at.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("hmip.news")

_NEWS_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "dynamic"
_NEWS_FILE = _NEWS_DIR / "news.json"

# RSS công khai (XML). Parser đơn giản lấy <item><title><link><description>.
_RSS_SOURCES: list[dict[str, str]] = [
    {"name": "VnExpress Kinh Doanh", "url": "https://vnexpress.net/rss/kinh-doanh.rss"},
    {"name": "CafeF", "url": "https://cafef.vn/kinh-te.rss"},
    {"name": "Đời sống Pháp luật", "url": "https://www.doisongphapluat.com/rss/kinh-doanh.rss"},
]

# Keyword lọc tin liên quan bia / giá / thuế
_KEYWORDS = [
    "bia", "heineken", "sabeco", "carlsberg", "tiger", "saigon", "hà nội",
    "thuế tiêu thụ đặc biệt", "ttđb", "rượu bia", "bia việt nam", "giá bia",
    "bia nhập khẩu", "bia hơi", "larue", "tuborg", "corona", "bia sư tử trắng",
    "bia trúc bạch", "bia huda", "vĩnh tuy",
]


def _fetch_rss(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 HMIP-news"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def _parse_items(xml: str, source: str) -> list[dict[str, Any]]:
    import re
    items = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
        block = m.group(1)
        title = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.S)
        link = re.search(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", block, re.S)
        desc = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", block, re.S)
        t = title.group(1).strip() if title else ""
        l = link.group(1).strip() if link else ""
        d = desc.group(1).strip() if desc else ""
        # strip html tags in desc
        d = re.sub(r"<[^>]+>", "", d)
        if not t or not l:
            continue
        low = (t + " " + d).lower()
        if any(k in low for k in _KEYWORDS):
            items.append({
                "title": t, "url": l, "snippet": d[:240],
                "source": source, "fetched_at": datetime.now(timezone.utc).isoformat(),
            })
    return items


def collect_beer_news(limit_per_source: int = 10) -> dict[str, Any]:
    """Quét RSS, trả {count, items, errors}. Append + dedupe vào news.json."""
    collected: list[dict[str, Any]] = []
    errors: list[str] = []
    for src in _RSS_SOURCES:
        try:
            xml = _fetch_rss(src["url"])
            items = _parse_items(xml, src["name"])[:limit_per_source]
            collected.extend(items)
            log.info("%s: %d tin bia", src["name"], len(items))
        except Exception as exc:
            errors.append(f"{src['name']}: {exc}")
            log.warning("RSS lỗi %s: %s", src["name"], exc)
    # dedupe + merge với file cũ
    existing = _load_existing()
    seen = {e.get("url") for e in existing}
    merged = list(existing)
    added = 0
    for it in collected:
        if it["url"] not in seen:
            merged.append(it)
            seen.add(it["url"])
            added += 1
    merged.sort(key=lambda x: x.get("fetched_at", ""), reverse=True)
    _NEWS_DIR.mkdir(parents=True, exist_ok=True)
    _NEWS_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"count": len(merged), "added": added, "errors": errors}


def _load_existing() -> list[dict[str, Any]]:
    if _NEWS_FILE.exists():
        try:
            data = json.loads(_NEWS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "items" in data:
                return data["items"]
        except Exception:
            pass
    return []


if __name__ == "__main__":
    print(json.dumps(collect_beer_news(), ensure_ascii=False, indent=2))
