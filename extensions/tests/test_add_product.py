"""Test cho tính năng thêm sản phẩm động (từ giao diện) + base_price tự động."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from extensions import db
from extensions.run_workflow import run_prc_001


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    p = str(tmp_path / "addprod.db")
    monkeypatch.setattr("extensions.db.DEFAULT_DB_PATH", p)
    db.init_db()
    return p


def test_add_product_persists(tmp_db):
    db.add_product("P999", "Test Beer", "TestBrand", "manual", None)
    prods = db.get_products()
    assert any(p["id"] == "P999" for p in prods)


def test_set_base_price_if_absent(tmp_db):
    db.add_product("P999", "Test", "B", "manual", None)
    bp = db.set_base_price_if_absent("P999", 12345.0)
    assert bp == 12345.0
    bp2 = db.set_base_price_if_absent("P999", 99999.0)
    assert bp2 == 12345.0


def test_new_product_auto_base_price(tmp_db, monkeypatch):
    db.add_product("PNEWB", "New Beer", "NewBrand", "manual", None)
    # sync vào ontology (giống API add_product) để enrich nhận diện được
    db.sync_to_ontology("PNEWB", "New Beer", "NewBrand")
    res = run_prc_001("PNEWB", "manual", persist=True)
    assert res["status"] == "COMPLETED"
    assert res["base_price"] is not None
    rows = db.get_history("PNEWB", path=tmp_db)
    assert rows
    assert abs(res["base_price"] - rows[0]["price"]) < 1e-6


def test_sync_to_ontology_appends(tmp_db, monkeypatch):
    repo = Path(__file__).resolve().parents[2]
    master = repo / "knowledge" / "master"
    prod_path = master / "products.json"
    brand_path = master / "brands.json"
    sku_path = master / "skus.json"
    def _load(p): return json.loads(p.read_text())
    def _dump(p, d): p.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    before = len(_load(prod_path))
    added = db.sync_to_ontology("PTESTX", "Tmp", "TmpBrand")
    after = len(_load(prod_path))
    if added:
        assert after == before + 1
        # cleanup mọi entry PTESTX khỏi 3 file master
        for fp in (prod_path, brand_path, sku_path):
            d = _load(fp)
            d = [x for x in d if x.get("id") != "PTESTX"
                 and x.get("product_id") != "PTESTX"
                 and x.get("brand_id") != "BRAND-PTESTX"]
            _dump(fp, d)
    # cleanup PNEWB đã sync trong test auto_base
    for fp in (prod_path, brand_path, sku_path):
        d = _load(fp)
        d = [x for x in d if x.get("id") != "PNEWB"
             and x.get("product_id") != "PNEWB"
             and x.get("brand_id") != "BRAND-PNEWB"]
        _dump(fp, d)
