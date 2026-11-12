"""Turn rows of the dbt `catalog` mart into OpenSearch documents."""
import duckdb

TEXT_FIELDS = ("product_name", "product_type", "brand", "category", "subcategory", "composition",
               "keywords", "description")


def doc_id(supplier: str, product_ref: str) -> str:
    return f"{supplier}:{product_ref}"


def row_to_doc(row: dict) -> dict:
    doc = {field: (row.get(field) or "") for field in TEXT_FIELDS}
    doc["id"] = doc_id(row["supplier"], row["product_ref"])
    doc["supplier"] = row["supplier"]
    doc["product_ref"] = row["product_ref"]
    doc["min_unit_price"] = row.get("min_unit_price")
    doc["in_stock_now"] = bool(row.get("in_stock_now"))
    doc["search_text"] = " | ".join(doc[f] for f in TEXT_FIELDS if doc[f])
    return doc


def load_catalog(db_path: str) -> list[dict]:
    # fetchall() keeps SQL NULL as None. pandas would turn it into NaN, which is truthy.
    con = duckdb.connect(db_path, read_only=True)
    try:
        cur = con.execute("select * from catalog order by supplier desc, product_ref")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()
    return [row_to_doc(r) for r in rows]
