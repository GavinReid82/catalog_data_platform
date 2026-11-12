import duckdb

from search.documents import TEXT_FIELDS, doc_id, load_catalog, row_to_doc


def test_doc_id_joins_supplier_and_ref():
    assert doc_id("vta", "12345") == "vta:12345"


def test_row_to_doc_fills_missing_text_with_empty_string():
    row = {"supplier": "vta", "product_ref": "1", "product_name": "Steel bottle",
           "category": None, "min_unit_price": 2.5, "in_stock_now": None}
    doc = row_to_doc(row)
    assert doc["id"] == "vta:1"
    assert doc["category"] == ""
    assert doc["in_stock_now"] is False
    assert doc["min_unit_price"] == 2.5
    assert set(TEXT_FIELDS) <= set(doc)


def test_search_text_skips_empty_fields():
    row = {"supplier": "vta", "product_ref": "1", "product_name": "Steel bottle",
           "category": "Drinkware", "composition": None}
    assert row_to_doc(row)["search_text"] == "Steel bottle | Drinkware"


def test_load_catalog_reads_the_catalog_table(tmp_path):
    db = str(tmp_path / "t.duckdb")
    con = duckdb.connect(db)
    con.execute("""
        create table catalog as select * from (values
          ('vta', 'A1', 'Steel bottle', 'bottle', 'Acme', 'Drinkware', 'Bottles', 'steel', 2.5, true),
          ('kes', 'B2', 'Cotton tote', 'bag', null, 'Bags', 'Totes', 'cotton', 1.1, false)
        ) t(supplier, product_ref, product_name, product_type, brand, category, subcategory,
            composition, min_unit_price, in_stock_now)
    """)
    con.close()
    docs = load_catalog(db)
    assert [d["id"] for d in docs] == ["vta:A1", "kes:B2"]
    assert docs[1]["brand"] == ""
