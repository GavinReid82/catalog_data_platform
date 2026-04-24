import os

import duckdb
import streamlit as st

st.set_page_config(page_title="MKO Product Catalog", layout="wide")
st.title("Makito Product Catalog")

DB_PATH = os.getenv("DUCKDB_PATH", "data/supply_integration.duckdb")


@st.cache_data
def load_catalog() -> "pd.DataFrame":
    con = duckdb.connect(DB_PATH, read_only=True)
    return con.execute("SELECT * FROM mko_catalog ORDER BY product_name").df()


df = load_catalog()

# --- Sidebar filters ---
st.sidebar.header("Filters")

in_stock_only = st.sidebar.checkbox("In stock now", value=False)

categories = sorted(df["category_name_1"].dropna().unique())
selected_category = st.sidebar.selectbox("Category", ["All"] + list(categories))

# --- Apply filters ---
filtered = df.copy()
if in_stock_only:
    filtered = filtered[filtered["in_stock_now"] == True]
if selected_category != "All":
    filtered = filtered[filtered["category_name_1"] == selected_category]

# --- Summary metrics ---
col1, col2, col3 = st.columns(3)
col1.metric("Products", len(filtered))
col2.metric("In stock", filtered["in_stock_now"].sum())
col3.metric(
    "Price range",
    f"€{filtered['min_unit_price'].min():.2f} – €{filtered['min_unit_price'].max():.2f}"
    if not filtered.empty else "—"
)

st.divider()

# --- Product table ---
display_cols = [
    "product_ref", "product_name", "product_type", "brand",
    "category_name_1", "category_name_2",
    "min_unit_price", "max_unit_price",
    "total_stock_qty", "in_stock_now", "earliest_available_date",
    "min_order_qty",
]

st.dataframe(
    filtered[display_cols].rename(columns={
        "product_ref": "Ref",
        "product_name": "Name",
        "product_type": "Type",
        "brand": "Brand",
        "category_name_1": "Category",
        "category_name_2": "Sub-category",
        "min_unit_price": "Min price (€)",
        "max_unit_price": "Max price (€)",
        "total_stock_qty": "Stock qty",
        "in_stock_now": "In stock",
        "earliest_available_date": "Available from",
        "min_order_qty": "MOQ",
    }),
    use_container_width=True,
    hide_index=True,
)
