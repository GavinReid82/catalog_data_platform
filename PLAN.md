# supply_integration — Standalone MKO Pipeline

## Overview

A standalone, containerised ELT pipeline that extracts product data from the Makito (MKO)
promotional products API, stores raw files in AWS S3, transforms with dbt + DuckDB,
and displays results in a Streamlit UI.

Built as a portfolio project mirroring the supply_integration platform at Helloprint,
using public/personal API access and no proprietary data.

---

## Architecture

```
Makito API
  → Python extractor
  → AWS S3 eu-south-2        (raw layer: XML + Parquet, date-partitioned, audit trail)
  → dbt + DuckDB             (reads from S3 via httpfs, writes to local .duckdb file)
  → Streamlit                (queries local DuckDB file)
  → Docker Compose           (ties everything together)
```

---

## Endpoints Used

| Endpoint | Format | Contents |
|---|---|---|
| `product` | manifest XML → CSVs | Full product catalog, variants, images |
| `price` | XML | 4-tier quantity-based pricing per product |
| `stock` | XML | Stock levels and availability dates per product |

---

## Data Model

### Staging (reads from S3 Parquet)
- `stg_mko_products` — core product fields, cast types, one row per product
- `stg_mko_variants` — one row per variant (matnr, colour, size), joined to product via ref
- `stg_mko_images` — one row per image URL, main image flagged
- `stg_mko_prices` — unpivoted from 4 tiers to one row per product/tier
- `stg_mko_stock` — one row per product/warehouse, with qty and availability date

### Marts
- `mko_catalog` — one row per product: name, category, main image, min price, total stock, in-stock flag

---

## Build Plan

| Day | Task |
|---|---|
| 1 | AWS account + S3 bucket + IAM user, project scaffold, venv |
| 2 | Python extractor — product manifest → CSVs, price XML, stock XML → S3 |
| 3 | dbt + DuckDB — staging models + mko_catalog mart |
| 4 | Streamlit UI — product catalog table, images, filters |
| 5 | Dockerfile + Docker Compose, end-to-end test |

---

## Stack

- **Python 3.11** — extraction and orchestration
- **boto3** — S3 uploads
- **dbt-duckdb** — transformation layer
- **DuckDB** — local query engine, reads Parquet from S3 via httpfs
- **Streamlit** — UI
- **Docker Compose** — local containerised runtime

---

## AWS Config

- Region: `eu-south-2` (Europe/Spain)
- Bucket: `supply-integration`
- S3 layout:
  ```
  supply-integration/
  └── mko/
      └── raw/
          ├── product/YYYY-MM-DD/*.parquet
          ├── price/YYYY-MM-DD/*.parquet
          └── stock/YYYY-MM-DD/*.parquet
  ```

---

## Running Locally (without Docker)

```bash
cp .env.example .env          # fill in credentials
pip install -r requirements.txt
python run_pipeline.py        # extract + transform
streamlit run ui/app.py       # open UI
```

## Running with Docker

```bash
cp .env.example .env
docker compose up pipeline    # extract + transform
docker compose up ui          # open UI on localhost:8501
```
