"""Test A+B: quét 4 trang VN bán bia bằng Camoufox.
- 3 trang thường: scrape_many_sync
- vietgourmet: scrape_age_gate (có cửa xác nhận tuổi 18+)
Sau đó lưu CSV + JSON.
"""
import asyncio
from camoufox_scraper import scrape_many_sync, scrape_age_gate, save_results

NORMAL = [
    "https://khotangbiabi.vn",
    "https://beerhouse.vn",
    "https://bianhagau.vn",
]
AGE_GATE = "https://vietgourmet.vn"


async def main():
    print("== Quét 3 trang thường ==")
    normal = await asyncio.to_thread(scrape_many_sync, NORMAL,
                                     wait_for="domcontentloaded", retries=3)

    print("== Quét vietgourmet (có cửa tuổi) ==")
    vg = await scrape_age_gate(AGE_GATE)

    results = normal + [vg]

    print("\n--- Kết quả ---")
    for r in results:
        ok = "OK " if r.ok else "FAIL"
        print(f"[{ok}] {r.url:26s} status={r.status:>3} title={r.title[:45]!r}")

    saved = save_results(results, base_path="bia_vn_scrape")
    print("\nĐã lưu:")
    print("  CSV :", saved["csv"])
    print("  JSON:", saved["json"])


if __name__ == "__main__":
    asyncio.run(main())
