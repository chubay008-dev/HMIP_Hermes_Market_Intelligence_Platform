import asyncio
from camoufox_scraper import scrape

async def main():
    targets = [
        ("https://example.com", "trang thường"),
        ("https://httpbin.org/headers", "API trả về header (xem UA)"),
        ("https://bot.sannysoft.com/", "trang chống-bot"),
    ]
    for url, label in targets:
        print(f"\n=== {label}: {url} ===")
        r = await scrape(url, wait_for="domcontentloaded")
        print("ok        :", r.ok)
        print("status    :", r.status)
        print("title     :", r.title)
        print("len(html) :", len(r.html))
        if not r.ok:
            print("error     :", r.error)
        else:
            # In một đoạn nhỏ để thấy nội dung thật
            snippet = r.text[:160].replace("\n", " ")
            print("text sniff:", snippet)

asyncio.run(main())
