"""Fake price API server — để test chế độ HMIP_COLLECT_MODE=http.

Trả JSON {price, brand, title, currency, province} cho mỗi product_id.
Chạy riêng:  python fake_price_api.py   (port 8777)
Sau đó app gọi HMIP_PRICE_API_BASE=http://127.0.0.1:8777/products
"""

from __future__ import annotations

import json
import random
from http.server import BaseHTTPRequestHandler, HTTPServer

# Giá tham chiếu thực tế (VND) để app so sánh quyết định
_PRICES = {
    "P123": {"title": "Saigon Special 330ml", "brand": "Saigon Beer", "price": 18500, "province": "HCMC"},
    "P456": {"title": "Heineken Lager 330ml", "brand": "Heineken", "price": 23500, "province": "HCMC"},
}


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # im lặng
        pass

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # route: /products/<pid>
        if self.path.startswith("/products/"):
            pid = self.path.rsplit("/", 1)[-1]
            if pid in _PRICES:
                base = _PRICES[pid]
                # dao động ±8% để thấy ALERT/IGNORE
                swing = random.uniform(-0.08, 0.08)
                price = round(base["price"] * (1 + swing))
                self._send({
                    "price": price,
                    "brand": base["brand"],
                    "title": base["title"],
                    "currency": "VND",
                    "province": base["province"],
                })
            else:
                self._send({"error": "unknown product"}, code=404)
        elif self.path == "/health":
            self._send({"status": "ok"})
        else:
            self._send({"error": "not found"}, code=404)


if __name__ == "__main__":
    print("Fake price API tại http://127.0.0.1:8777/products/<pid>")
    HTTPServer(("127.0.0.1", 8777), _H).serve_forever()
