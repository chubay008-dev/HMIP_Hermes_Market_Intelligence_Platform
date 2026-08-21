"""
camoufox_scraper.py — Helper tái dùng để scraping bằng Camoufox (Firefox chống-detect).

Đặc điểm:
- Headless mặc định (chạy được trên server không màn hình)
- Fingerprint ngẫu nhiên tự động (os_randomize + humanize) → khó bị bot phát hiện
- Có retry + timeout, trả về kết quả có cấu trúc (dict)
- Hỗ trợ proxy tùy chọn, chặn tài nguyên nặng (ảnh/font) để nhanh hơn
- Cung cấp cả bản async (khuyên dùng) và sync (wrapper)

Cách dùng:
    source /home/kali/camoufox-venv/bin/activate
    from camoufox_scraper import scrape

    # Async
    import asyncio
    res = asyncio.run(scrape("https://example.com"))
    print(res["title"], res["status"], len(res["html"]))

    # Sync
    from camoufox_scraper import scrape_sync
    res = scrape_sync("https://example.com")
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, asdict
from typing import Optional


# ----------------------------------------------------------------------------
# Cấu hình mặc định
# ----------------------------------------------------------------------------
DEFAULT_TIMEOUT_MS = 30_000      # timeout mỗi thao tác (ms)
DEFAULT_RETRIES = 3              # số lần thử lại nếu fail
USER_AGENTS_OS = ["windows", "macos", "linux"]   # Camoufox random OS mỗi lần chạy


@dataclass
class ScrapeResult:
    url: str
    final_url: Optional[str]
    status: Optional[int]
    title: Optional[str]
    html: str
    text: str
    ok: bool
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _launch_kwargs(block_resources: bool, os_list, humanize) -> dict:
    """Build kwargs truyền vào AsyncCamoufox (API chuẩn của camoufox>=0.5)."""
    kw = {
        "headless": True,
        "os": os_list,                  # random OS fingerprint mỗi lần chạy
        "humanize": humanize,           # chuyển động chuột/bàn phím giả người
        "block_images": block_resources,  # built-in: chặn ảnh (nhẹ, tin cậy)
    }
    return kw


async def scrape(
    url: str,
    *,
    wait_for: str = "domcontentloaded",
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    retries: int = DEFAULT_RETRIES,
    block_resources: bool = False,   # CẢNH BÁO: chặn ảnh dễ bị WAF lớn phát hiện; để False cho an toàn
    os_randomize: bool = True,
    humanize: bool = True,
    proxy: Optional[str] = None,
) -> ScrapeResult:
    """
    Mở `url` bằng Camoufox và trả về ScrapeResult.

    - wait_for: 'domcontentloaded' | 'load' | 'networkidle'
    - block_resources=True: chặn image/font/stylesheet để tải nhanh, giữ lại document+scipt
    - proxy: "http://user:pass@host:port" (tùy chọn)
    - os_randomize + humanize: fingerprint ngẫu nhiên + hành vi giả người
    """
    from camoufox.async_api import AsyncCamoufox

    last_err: Optional[str] = None
    for attempt in range(1, retries + 1):
        try:
            kw = _launch_kwargs(
                block_resources,
                random.choice(USER_AGENTS_OS) if os_randomize else USER_AGENTS_OS,
                humanize,
            )
            if proxy:
                kw["proxy"] = {"server": proxy}

            async with AsyncCamoufox(**kw) as browser:
                page = await browser.new_page()
                page.set_default_timeout(timeout_ms)

                resp = await page.goto(url, wait_until=wait_for, timeout=timeout_ms)
                status = resp.status if resp else None
                title = await page.title()
                html = await page.content()
                text = (await page.inner_text("body")).strip() if await _has_body(page) else ""
                return ScrapeResult(
                    url=url,
                    final_url=page.url,
                    status=status,
                    title=title,
                    html=html,
                    text=text,
                    ok=True,
                )
        except Exception as e:  # noqa: BLE001 — muốn retry mọi lỗi browser
            last_err = f"{type(e).__name__}: {e}"
            # Tránh giống hệt fingerprint hai lần thất bại liên tiếp
            await asyncio.sleep(random.uniform(0.5, 2.0))

    return ScrapeResult(
        url=url, final_url=None, status=None, title=None,
        html="", text="", ok=False, error=f"failed after {retries} tries: {last_err}",
    )


async def _has_body(page) -> bool:
    try:
        await page.wait_for_selector("body", timeout=5_000)
        return True
    except Exception:  # noqa: BLE001
        return False


def scrape_sync(url: str, **kwargs) -> ScrapeResult:
    """Wrapper đồng bộ của scrape() — tiện khi viết script tuần tự."""
    return asyncio.run(scrape(url, **kwargs))


async def scrape_age_gate(
    url: str,
    *,
    confirm_selector: str = ".age-gate-submit-yes",
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    **kwargs,
) -> ScrapeResult:
    """
    Mở trang, nếu gặp cửa xác nhận tuổi (age gate) thì click nút xác nhận
    (mặc định selector của age gate WordPress: .age-gate-submit-yes),
    chờ navigation submit form, rồi đọc nội dung thật.
    Dùng cho các web bán rượu/bia bắt confirm 18+.
    """
    from camoufox.async_api import AsyncCamoufox

    kw = _launch_kwargs(
        kwargs.pop("block_resources", False),
        random.choice(USER_AGENTS_OS) if kwargs.get("os_randomize", True) else USER_AGENTS_OS,
        kwargs.get("humanize", True),
    )
    if (proxy := kwargs.pop("proxy", None)):
        kw["proxy"] = {"server": proxy}

    async with AsyncCamoufox(**kw) as browser:
        page = await browser.new_page()
        page.set_default_timeout(timeout_ms)
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        status = resp.status if resp else None

        # Thử click nút xác nhận tuổi (form submit -> navigation)
        try:
            async with page.expect_navigation(timeout=timeout_ms):
                await page.click(confirm_selector)
        except Exception:  # noqa: BLE001 — không có cửa tuổi / nav trễ thì bỏ qua
            pass
        await page.wait_for_timeout(2_000)

        title = await page.title()
        html = await page.content()
        text = (await page.inner_text("body")).strip() if await _has_body(page) else ""
        return ScrapeResult(
            url=url, final_url=page.url, status=status,
            title=title, html=html, text=text, ok=True,
        )


# ----------------------------------------------------------------------------
# Quét hàng loạt + lưu kết quả
# ----------------------------------------------------------------------------
async def scrape_many(
    urls: list[str],
    *,
    max_concurrency: int = 3,
    **kwargs,
) -> list[ScrapeResult]:
    """
    Quét nhiều URL song song (giới hạn đồng thời để không bị IP ban).
    Trả về list[ScrapeResult] theo đúng thứ tự urls.
    """
    sem = asyncio.Semaphore(max_concurrency)

    async def _one(u: str) -> ScrapeResult:
        async with sem:
            return await scrape(u, **kwargs)

    return await asyncio.gather(*(_one(u) for u in urls))


def scrape_many_sync(urls: list[str], **kwargs) -> list[ScrapeResult]:
    """Wrapper đồng bộ của scrape_many()."""
    return asyncio.run(scrape_many(urls, **kwargs))


def save_results(results: list[ScrapeResult], base_path: str = "scrape_output") -> dict:
    """
    Lưu kết quả ra CSV + JSON.
    - base_path không cần đuôi; sinh: <base_path>.csv và <base_path>.json
    Trả về dict {'csv': path, 'json': path}.
    """
    import csv
    import json

    rows = [r.to_dict() for r in results]
    csv_path = base_path + ".csv"
    json_path = base_path + ".json"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        for row in rows:
            # html/text có thể rất dài -> cắt khi lưu CSV cho gọn
            r = dict(row)
            r["html"] = (r["html"] or "")[:5000]
            r["text"] = (r["text"] or "")[:2000]
            writer.writerow(r)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    return {"csv": csv_path, "json": json_path}
