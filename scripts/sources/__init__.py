# -*- coding: utf-8 -*-
"""Adapters thu thập giá từ các nguồn ngoài. Mỗi adapter trả list dict:
    {product_id, name, price_case_vnd, price_single_vnd, source, confidence, url}
và ghi raw vào data/raw/<source>.json (không ghi đè master).
"""
