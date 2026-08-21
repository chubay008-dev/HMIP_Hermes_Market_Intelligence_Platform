import asyncio
from camoufox.async_api import AsyncCamoufox

async def main():
    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()
        # 1) Trang thường
        await page.goto("https://example.com", wait_until="domcontentloaded")
        title = await page.title()
        ua = await page.evaluate("navigator.userAgent")
        print("=== TEST 1: example.com ===")
        print("Title      :", title)
        print("User-Agent :", ua)
        print("OK example.com\n")

        # 2) Trang chống-bot (kiểm tra stealth)
        await page.goto("https://bot.sannysoft.com/", wait_until="networkidle")
        txt = await page.inner_text("body")
        print("=== TEST 2: bot.sannysoft.com (stealth check) ===")
        for line in txt.splitlines():
            if "webdriver" in line.lower() or "PASS" in line or "FAIL" in line:
                print("  ", line.strip())
        print("OK bot.sannysoft.com")

asyncio.run(main())
