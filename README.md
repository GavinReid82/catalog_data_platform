# catalog_data_platform

A multi-supplier ELT pipeline and catalogue-management tool for promotional
goods. It extracts product data from supplier feeds, stores raw files in AWS S3,
transforms them with dbt + DuckDB, and serves two workflows through a Streamlit
UI: one-off order configuration, and PCM export for website catalogues.

Built as a public, inspectable portfolio counterpart to a supplier-integration
platform I built at HelloPrint. The two feed sources here — **Vantora** (XML
feeds) and **Kestrel** (XLSX feeds) — are fictional stand-ins; the product data
is real but carries no supplier identity.

---

## Architecture

```
Supplier feeds (Vantora — XML, Kestrel — XLSX, ...)
  ↓
SupplierExtractor adapters       extractor/
  ↓
AWS S3  (Parquet, date-partitioned, per-supplier prefix)
  ↓
dbt + DuckDB                     dbt_project/models/
  staging  →  intermediate  →  canonical marts
  ↓
Streamlit UI                     ui/
  Landing · Catalogue · Configure Order · Category Management
```

---

## Features

### Extraction layer

- **VTA:** fetches five XML feeds (product catalogue, tiered pricing, stock levels, print options, print technique prices)
- **KES:** fetches five XLSX feeds (product/variants in one file, pricing, print options, print prices, stock); normalises headers on read
- Uploads raw data to S3 as date-partitioned Parquet files
- `SupplierExtractor` abstract base class — adding a new supplier requires one new adapter class, zero changes to the orchestrator

### dbt transformation layer

33 models across three layers, all targeting DuckDB via the `dbt-duckdb` adapter:

| Layer | Type | Purpose |
|---|---|---|
| `stg_vta_*` (6 models) | view | Type casting and light cleaning from VTA S3 Parquet |
| `stg_kes_*` (5 models) | view | Type casting and unit conversion from KES S3 Parquet |
| `int_vta_*` (6 models) | view | Normalise to canonical shape, add `supplier='vta'` |
| `int_kes_*` (6 models) | view | Normalise to canonical shape, add `supplier='kes'`; `int_kes_products` derived from variants |
| `catalog`, `variants`, `prices`, `print_options`, `print_prices` | table | Canonical, supplier-agnostic (conditional Jinja unions — KES active when `KES_BASE_URL` is set) |
| `vta_*` (5 models) | table | Supplier-filtered views of the canonical tables |

Seeds: `carriers.csv`, `vta_carrier_zones.csv`, `pcm_templates.csv`, `kes_availability_thresholds.csv`. KES models carry `{{ config(tags=["kes"]) }}` — use `dbt run --exclude tag:kes` for VTA-only builds.

DuckDB reads S3 Parquet directly via the `httpfs` extension — no local copy of raw data.

### Streamlit UI

| Page | Purpose |
|---|---|
| Landing | Routes to Bespoke or Category Management |
| Catalogue | Browse products with category/price filters, images, tiered pricing, variant details |
| Configure Order | 5-step Bespoke flow: product → variant → quantity → print options → carrier → supplier reference |
| Category Management | Select products by PCM template, auto-generate slugs, assign quantity codes, configure print options, export CSV |

---

## Stack

- **Python 3.11** — extraction and orchestration
- **boto3** — S3 uploads
- **requests + tenacity** — HTTP with retry and exponential backoff
- **dbt-duckdb 1.8** — transformation layer
- **DuckDB** — analytical engine, reads Parquet from S3 via httpfs
- **Streamlit** — UI
- **Apache Airflow + Astronomer Astro** — DAG orchestration (daily schedule, TaskFlow API)
- **PyYAML** — business logic config
- **Docker Compose** — containerised runtime
- **GitHub Actions** — CI (pytest + dbt parse on every push)

---

## Project structure

```
catalog_data_platform/
├── run_pipeline.py               # extract → dbt seed/run/test (manual / local)
├── airflow/
│   ├── dags/supply_integration.py  # TaskFlow DAG — daily schedule, seed hash skip
│   ├── docker-compose.override.yml # mounts project root + injects .env into Astro
│   └── requirements.txt
├── .github/workflows/ci.yml      # pytest + dbt parse on push/PR
├── extractor/
│   ├── base.py                   # SupplierConfig dataclass + SupplierExtractor ABC
│   ├── vta.py                    # VtaExtractor (XML feeds)
│   ├── kes.py                    # KesExtractor (XLSX feeds)
│   ├── endpoints.py              # VTA fetch_* functions
│   ├── client.py                 # HTTP retry logic
│   └── loader.py                 # S3 upload
├── dbt_project/
│   ├── models/
│   │   ├── staging/              # stg_vta_*.sql (6), stg_kes_*.sql (5)
│   │   ├── intermediate/         # int_vta_*.sql (6), int_kes_*.sql (6)
│   │   └── marts/                # canonical (5) + supplier-specific (5)
│   └── seeds/                    # carriers, vta_carrier_zones, pcm_templates, kes_availability_thresholds
├── ui/
│   ├── app.py                    # st.navigation router + sidebar page_links
│   ├── db.py                     # shared query() function
│   ├── supplier_reference.py     # build() dispatcher — VTA + KES
│   ├── basket.py                 # session state basket
│   └── pages/
│       ├── 0_Home.py             # landing page
│       ├── 1_Catalog.py
│       ├── 2_Configure_Order.py
│       └── 3_Catman.py
└── business_logic/
    └── quantity_codes.yaml       # 33 VTA PCM template quantity code defaults
```

---

## Running locally

**1. Set up credentials**

```bash
cp .env.example .env
# Fill in AWS credentials, S3 bucket, and VTA API URLs
```

Required variables:

```
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_DEFAULT_REGION=eu-south-2
S3_BUCKET=catalog-data-platform
VTA_BASE_URL
VTA_URL_SUFFIX_PRODUCT
VTA_URL_SUFFIX_PRICE
VTA_URL_SUFFIX_STOCK
VTA_URL_SUFFIX_PRINT
VTA_URL_SUFFIX_PRINT_PRICE
DUCKDB_PATH          # optional, defaults to data/catalog_data_platform.duckdb
```

**2. Install dependencies**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**3. Run the pipeline**

```bash
python run_pipeline.py
```

This extracts all five VTA feeds, uploads to S3, then runs `dbt seed && dbt run && dbt test`.

**4. Launch the UI**

```bash
streamlit run ui/app.py
```

Open [http://localhost:8501](http://localhost:8501).

**Note:** DuckDB is single-writer. Stop the UI before re-running the pipeline.

---

## Running with Airflow (Astronomer Astro)

The pipeline runs daily on a schedule via an Airflow DAG. To start the Airflow environment locally:

```bash
cd airflow
astro dev start        # boots scheduler, webserver, triggerer, and Postgres in Docker
```

The Airflow UI is available at [http://localhost:8081](http://localhost:8081). The `supply_integration` DAG runs `@daily` — trigger it manually from the UI or with:

```bash
astro dev run dags trigger supply_integration
```

The `docker-compose.override.yml` mounts the project root into all containers and injects credentials from the parent `.env` file. No image rebuild is needed when editing models or the DAG.

---

## Running with Docker Compose

```bash
cp .env.example .env   # fill in credentials
docker compose up
```

The `pipeline` service runs `run_pipeline.py` first. The `ui` service starts after and serves Streamlit on port 8501.

---

## Adding a new supplier

The architecture is designed so that adding supplier XYZ requires changes in exactly five places and nowhere else:

1. `extractor/xyz.py` — implement `XyzExtractor(SupplierExtractor)` with a `run(date)` method
2. `dbt_project/models/staging/stg_xyz_*.sql` — type-cast the raw S3 feeds
3. `dbt_project/models/intermediate/int_xyz_*.sql` — normalise to canonical shape, add `supplier = 'xyz'`
4. `dbt_project/models/marts/*.sql` — add a conditional Jinja union branch (`{% if env_var('XYZ_BASE_URL', '') != '' %}`) to each canonical mart
5. `ui/supplier_reference.py` — add an `_xyz()` case to the `build()` dispatcher

`run_pipeline.py` and all UI pages require no changes. KES demonstrates this pattern end-to-end.

---

## Status

| Component | Status |
|---|---|
| AWS S3 + IAM | Done |
| Python extractor (VTA — 5 XML feeds) | Done |
| Python extractor (KES — 5 XLSX feeds) | Done |
| dbt staging layer (VTA: 6 models, KES: 5 models) | Done |
| dbt intermediate layer (VTA: 6 models, KES: 6 models) | Done |
| dbt canonical marts (5 tables, conditional Jinja unions) | Done |
| dbt seeds (carriers, carrier zones, pcm_templates, kes_availability_thresholds) | Done |
| SupplierExtractor ABC + VtaExtractor + KesExtractor | Done |
| Streamlit UI (4 pages + landing) | Done |
| Shopping basket (session state, CSV export) | Done |
| Dockerfile + Docker Compose | Done |
| Unit tests for extractor layer (28 tests) | Done |
| Airflow DAG (Astronomer Astro, TaskFlow API, seed hash optimisation) | Done |
| CI/CD with GitHub Actions | Done |
