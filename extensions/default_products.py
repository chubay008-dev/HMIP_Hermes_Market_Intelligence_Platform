# extensions/default_products.py
# Catalog sản phẩm bia mặc định — hardcode để mỗi lần deploy đều có sẵn.
# Nguồn: danh sách market map bia VN + nhập khẩu (từ ChatGPT, 2026-08-11).
# Mỗi entry: product_id -> {brand, product_name, ref_price, province}
# ref_price là giá tham chiếu demo (VND), dùng làm base_price tự động khi quét.

DEFAULT_PRODUCTS: dict[str, dict[str, str | float]] = {
    # --- Bia nội / phổ biến ---
    "P123": {"brand": "Saigon Beer", "product_name": "Saigon Special 330ml", "ref_price": 18000.0, "province": "HCMC"},
    "P456": {"brand": "Heineken", "product_name": "Heineken Lager 330ml", "ref_price": 22000.0, "province": "HCMC"},
    "P789": {"brand": "Tiger", "product_name": "Tiger Beer 330ml", "ref_price": 20000.0, "province": "HCMC"},
    "P012": {"brand": "Habeco", "product_name": "Bia Ha Noi 450ml", "ref_price": 15000.0, "province": "Hanoi"},
    "P555": {"brand": "Saigon Beer", "product_name": "Saigon Export 330ml", "ref_price": 17000.0, "province": "HCMC"},
    "P333": {"brand": "Larue", "product_name": "Bia Larue 330ml", "ref_price": 16000.0, "province": "Danang"},
    "P777": {"brand": "Sapporo", "product_name": "Sapporo Premium 330ml", "ref_price": 25000.0, "province": "HCMC"},
    "P888": {"brand": "Budweiser", "product_name": "Budweiser 330ml", "ref_price": 24000.0, "province": "HCMC"},

    # --- Tuborg (Carlsberg VN) ---
    "PTBG": {"brand": "Tuborg", "product_name": "Tuborg 330ml", "ref_price": 19000.0, "province": "HCMC"},
    "PTBG_G": {"brand": "Tuborg", "product_name": "Tuborg Green 330ml", "ref_price": 19000.0, "province": "HCMC"},
    "PTBG_C": {"brand": "Tuborg", "product_name": "Tuborg Classic 330ml", "ref_price": 19500.0, "province": "HCMC"},
    "PTBG_D": {"brand": "Tuborg", "product_name": "Tuborg Gold 330ml", "ref_price": 21000.0, "province": "HCMC"},

    # --- Bia nhập khẩu Tây Ban Nha ---
    "PESP_EG": {"brand": "Estrella", "product_name": "Estrella Galicia 330ml", "ref_price": 35000.0, "province": "HCMC"},
    "PESP_ED": {"brand": "Estrella", "product_name": "Estrella Damm 330ml", "ref_price": 33000.0, "province": "HCMC"},
    "PESP_MH": {"brand": "Mahou", "product_name": "Mahou 330ml", "ref_price": 34000.0, "province": "HCMC"},
    "PESP_SM": {"brand": "San Miguel", "product_name": "San Miguel 330ml", "ref_price": 32000.0, "province": "HCMC"},

    # --- Bia nhập khẩu Ý ---
    "PITA_PN": {"brand": "Peroni", "product_name": "Peroni Nastro Azzurro 330ml", "ref_price": 38000.0, "province": "HCMC"},
    "PITA_P": {"brand": "Peroni", "product_name": "Peroni 330ml", "ref_price": 36000.0, "province": "HCMC"},
    "PITA_MO": {"brand": "Moretti", "product_name": "Moretti 330ml", "ref_price": 37000.0, "province": "HCMC"},
    "PITA_BM": {"brand": "Birra Messina", "product_name": "Birra Messina 330ml", "ref_price": 35000.0, "province": "HCMC"},
    "PITA_MN": {"brand": "Menabrea", "product_name": "Menabrea 330ml", "ref_price": 39000.0, "province": "HCMC"},

    # --- Bia nhập khẩu Ireland (Guinness) ---
    "PIRE_GD": {"brand": "Guinness", "product_name": "Guinness Draught 440ml", "ref_price": 42000.0, "province": "HCMC"},
    "PIRE_GE": {"brand": "Guinness", "product_name": "Guinness Extra Stout 440ml", "ref_price": 40000.0, "province": "HCMC"},
    "PIRE_GF": {"brand": "Guinness", "product_name": "Guinness Foreign Extra Stout 440ml", "ref_price": 41000.0, "province": "HCMC"},
    "PIRE_G0": {"brand": "Guinness", "product_name": "Guinness 0.0 440ml", "ref_price": 39000.0, "province": "HCMC"},

    # --- Bia nhập khẩu Mexico / LATAM ---
    "PMEX_CO": {"brand": "Corona", "product_name": "Corona Extra 330ml", "ref_price": 30000.0, "province": "HCMC"},
    "PMEX_CC": {"brand": "Corona", "product_name": "Corona Cero 330ml", "ref_price": 31000.0, "province": "HCMC"},
    "PMEX_ME": {"brand": "Modelo", "product_name": "Modelo Especial 330ml", "ref_price": 32000.0, "province": "HCMC"},
    "PMEX_NM": {"brand": "Modelo", "product_name": "Negra Modelo 330ml", "ref_price": 33000.0, "province": "HCMC"},
    "PMEX_SO": {"brand": "Sol", "product_name": "Sol 330ml", "ref_price": 28000.0, "province": "HCMC"},
    "PMEX_PA": {"brand": "Pacifico", "product_name": "Pacifico 330ml", "ref_price": 29000.0, "province": "HCMC"},
    "PMEX_DE": {"brand": "Dos Equis", "product_name": "Dos Equis 330ml", "ref_price": 30000.0, "province": "HCMC"},

    # --- Bia nhập khẩu Nga / Đông Âu ---
    "PRUS_BA": {"brand": "Baltika", "product_name": "Baltika 330ml", "ref_price": 27000.0, "province": "HCMC"},
    "PRUS_B0": {"brand": "Baltika", "product_name": "Baltika 0 (khong con) 330ml", "ref_price": 26000.0, "province": "HCMC"},

    # --- Bia khong con / Low-alcohol ---
    "PZ_HN": {"brand": "Heineken", "product_name": "Heineken 0.0 330ml", "ref_price": 20000.0, "province": "HCMC"},
    "PZ_BW": {"brand": "Budweiser", "product_name": "Budweiser Zero 330ml", "ref_price": 22000.0, "province": "HCMC"},
    "PZ_ER": {"brand": "Erdinger", "product_name": "Erdinger Alkoholfrei 330ml", "ref_price": 45000.0, "province": "HCMC"},
    "PZ_AS": {"brand": "Asahi", "product_name": "Asahi Dry Zero 330ml", "ref_price": 30000.0, "province": "HCMC"},
    "PZ_BK": {"brand": "Beck's", "product_name": "Beck's Blue 330ml", "ref_price": 29000.0, "province": "HCMC"},
}
