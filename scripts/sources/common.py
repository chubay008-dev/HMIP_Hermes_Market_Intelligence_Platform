# -*- coding: utf-8 -*-
"""Helper dùng chung cho các adapter nguồn."""
from __future__ import annotations
import datetime
import json
import re
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw"
MASTER = REPO / "knowledge" / "master"

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def name_tokens(s: str) -> list[str]:
    stop = {"bia", "the", "lon", "chai", "thung", "loc", "ket", "ml", "cl", "cua",
            "combo", "hop", "quà", "tet", "hang", "nhap", "khau"}
    words = re.findall(r"[a-z0-9]+", norm(s))
    return [w for w in words if w not in stop and len(w) >= 2]


def load_products() -> list[dict]:
    d = json.loads((MASTER / "products.json").read_text(encoding="utf-8"))
    return d.get("products", d) if isinstance(d, dict) else d


def extract_vnd(text: str) -> list[int]:
    """Bắt các cụm tiền VND trong text. Trả list int."""
    out = []
    for n in re.findall(r"(\d{1,3}(?:[.,]\d{3})+|\d{4,})\s*(?:₫|đ|d|vnd|vnđ)", text, re.I):
        n = n.replace(".", "").replace(",", "")
        try:
            v = int(n)
            if 5000 <= v <= 5_000_000:
                out.append(v)
        except ValueError:
            pass
    return out


def save_raw(source: str, items: list[dict]) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    payload = {
        "source": source,
        "captured_date": today,
        "count": len(items),
        "items": items,
    }
    p = RAW / f"{source}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
