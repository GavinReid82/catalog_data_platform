# Day 10 — S3 Partition Strategy, Airflow Orchestration, and Variants Grain Fix

## What I Did

Four distinct pieces of work this session:

1. **Replaced S3 glob reads with date-specific partition reads** across all staging models.
2. **Added automatic S3 partition cleanup** so stale data is removed after each run.
3. **Built an Airflow DAG with Astronomer Astro** to replace `run_pipeline.py` as the pipeline orchestrator.
4. **Corrected the variants mart grain** — `variant_id` alone is not a unique key.

---

1. **Replaced S3 glob reads with date-specific partition reads** across all staging models.
2. **Added automatic S3 partition cleanup** so stale data is removed after each run.
3. **Corrected the variants mart grain** — `variant_id` alone is not a unique key.

---

## Core Concepts

### The S3 glob problem and the `run_date` variable

The original staging models read from S3 using a wildcard partition:

```sql
select * from read_parquet('s3://{{ env_var("S3_BUCKET") }}/mko/raw/stock/*/stock.parquet')
```

The `*` matches any date directory. This was the cause of the deduplication bug from
Day 8: after two pipeline runs, every row appeared twice because the query read both
`2026-04-28/` and `2026-04-29/`. The fix at the time was `QUALIFY ROW_NUMBER()` in
the intermediate models — treating the symptom, not the cause.

The correct fix is to read only the partition for the current run:

```sql
select * from read_parquet('s3://{{ env_var("S3_BUCKET") }}/mko/raw/stock/{{ var("run_date") }}/stock.parquet')
```

`{{ var("run_date") }}` is a dbt variable, passed at runtime via:

```bash
dbt run --project-dir dbt_project --profiles-dir dbt_project --vars '{"run_date": "2026-04-30"}'
```

The distinction from `env_var`: `var()` is passed by the caller of `dbt run`, not the
shell environment. `env_var()` reads OS-level environment variables. The right choice
depends on what controls the value — the shell (env var) or the pipeline orchestrator
(dbt var). Since `run_date` is determined by `run_pipeline.py`, passing it as a dbt
`--vars` argument is semantically correct: the orchestrator owns the date, not the shell.

This change is applied to all 11 staging models (5 MKO + 6 XDC). The intermediate and
mart models are unchanged — they read from the staging views, which are now date-scoped.

**Effect:** each dbt run now reads exactly one day's data. No deduplication needed in
intermediate models. The QUALIFY approach in `int_mko_variants.sql` (added Day 8) can
be removed once the pipeline is confirmed passing with date-specific reads.

---

### S3 partition retention

Running the pipeline daily accumulates Parquet files across all date directories. Without
cleanup, S3 costs grow and old data could re-enter reads if the glob pattern is ever
restored accidentally.

The retention policy: keep today + yesterday, delete partitions older than 2 days.

```python
# extractor/loader.py
def delete_partition(bucket: str, prefix: str) -> None:
    """Delete all S3 objects under prefix (e.g. 'mko/raw/stock/2026-04-28/')."""
    client = _s3()
    paginator = client.get_paginator("list_objects_v2")
    keys = [
        {"Key": obj["Key"]}
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
        for obj in page.get("Contents", [])
    ]
    if not keys:
        return
    client.delete_objects(Bucket=bucket, Delete={"Objects": keys})
```

The S3 `delete_objects` API can handle up to 1,000 keys per call. For a feed with one
Parquet file per partition that limit is never approached, but the paginator-based
approach scales correctly if a feed ever writes multiple files per partition.

Each extractor calls `_delete_old_partition()` at the end of its `run()`:

```python
def _delete_old_partition(self, sup: str, today: str) -> None:
    stale = (date_type.fromisoformat(today) - timedelta(days=2)).isoformat()
    for feed in ("product", "price", "print", "stock"):
        delete_partition(self.bucket, f"{sup}/raw/{feed}/{stale}/")
```

`timedelta(days=2)` relative to today — not yesterday — is deliberate. Keeping yesterday
allows a re-run from the previous partition if today's extraction fails, without
accumulating indefinite history.

The cleanup runs *after* upload, so a crash mid-extraction cannot delete data before
the new partition is written.

---

### The variants grain problem

The `variants` mart previously declared `variant_id` as a unique key and carried a
dbt `unique` test to enforce it. This assumption failed: MKO uses `matnr` as its
`variant_id`, and the same `matnr` can appear under multiple `product_ref` values (MKO
groups products into product families that share components).

The correct grain for the `variants` mart is `(supplier, product_ref, variant_id)`.

Changes:

**`dbt_project/models/marts/schema.yml`** — Updated the description and removed the
`unique` test from `variant_id`:

```yaml
- name: variants
  description: >
    One row per supplier + product + variant. Canonical variant mart unioning all suppliers.
    Grain: (supplier, product_ref, variant_id) — the same variant_id can appear under
    multiple products (MKO shares matnr across product groups).
  columns:
    - name: variant_id
      tests:
        - not_null
        # unique removed — matnr is shared across MKO product groups
```

**`dbt_project/tests/test_variants_unique_key.sql`** — Updated to test the composite
key:

```sql
select
    supplier,
    product_ref,
    variant_id,
    count(*) as cnt
from {{ ref('variants') }}
group by supplier, product_ref, variant_id
having count(*) > 1
```

This is the correct pattern for testing composite unique keys in dbt when the out-of-box
`unique` test only covers single columns. The query returns rows on failure — an empty
result means the test passes.

---

### Airflow with Astronomer Astro

`run_pipeline.py` is a script: run it manually, and it runs once. Airflow is an
orchestrator: schedule the DAG, and it runs itself every day, retries on failure, and
gives you a UI to inspect each run. Replacing the script with a DAG was the "Airflow
DAG" item that had been on the project plan since Day 5.

**Astronomer Astro** is the local development environment for Airflow. Instead of
installing Airflow with `pip`, I initialised a project with `astro dev init` inside the
`airflow/` directory. `astro dev start` boots the full Airflow stack (scheduler, webserver,
triggerer, Postgres metadata DB) in Docker. The webserver is available at
`localhost:8081` (configured in `airflow/.astro/config.yaml`).

The Astro `Dockerfile` is a single line:

```dockerfile
FROM quay.io/astronomer/astro-runtime:12.0.0
```

`astro-runtime` is a pre-built Airflow image maintained by Astronomer. Python
dependencies for the pipeline go in `airflow/requirements.txt` — Astro installs them
into the image at build time.

---

#### Project code inside Airflow containers

The extractor code and dbt project live in the project root, not inside `airflow/`. To
make them available to the Airflow containers without copying or packaging, I mount the
project root as a volume via `airflow/docker-compose.override.yml`:

```yaml
services:
  scheduler:
    env_file: ../.env
    environment:
      DUCKDB_PATH: /usr/local/project/data/catalog_data_platform.duckdb
    volumes:
      - ../:/usr/local/project
  webserver:
    ...
  triggerer:
    ...
```

`env_file: ../.env` injects credentials (AWS keys, supplier URLs) from the parent
directory's `.env` file. This avoids duplicating secrets into the Airflow project.
The `DUCKDB_PATH` environment variable tells dbt-duckdb where to write the database
inside the container's mounted volume.

The volume mount means changes to the extractor or dbt models take effect immediately
on the next task run — no image rebuild required during development.

---

#### DAG structure — TaskFlow API

The DAG uses Airflow's **TaskFlow API** (`@dag`, `@task` decorators) rather than
traditional operators like `PythonOperator`. TaskFlow is the modern, idiomatic approach:
task functions are plain Python, and the decorator handles task registration, XCom,
and dependencies.

```python
@dag(
    dag_id="supply_integration",
    schedule="@daily",
    start_date=pendulum_datetime(2025, 1, 1),
    catchup=False,
)
def supply_integration():
    with TaskGroup("extract") as extract_group:
        ...
    with TaskGroup("transform") as transform_group:
        ...
    extract_group >> transform_group
```

`catchup=False` means Airflow will not backfill historical runs when first deployed.
`pendulum_datetime` is the correct type for `start_date` — Airflow requires a
timezone-aware datetime and pendulum handles that cleanly.

**TaskGroups** (`with TaskGroup("extract")`) group related tasks visually in the Airflow
UI without affecting execution logic. The full task graph:

```
supply_integration.extract.extract_mko ──┐
                                         ├──► supply_integration.transform.dbt_seed
supply_integration.extract.extract_xdc ──┘        ↓
                                          supply_integration.transform.dbt_run
                                                   ↓
                                          supply_integration.transform.dbt_test
```

The two extract tasks run in parallel. Both must succeed before the transform group starts.

---

#### XDC conditional skip — early return vs BranchPythonOperator

`extract_xdc` checks for `XDC_BASE_URL` and returns early if it is absent:

```python
@task
def extract_xdc():
    if not os.environ.get("XDC_BASE_URL"):
        log.info("XDC_BASE_URL not set — skipping XDC extraction.")
        return
    ...
```

This is simpler than using `BranchPythonOperator`, which would require a separate
"skip" task and explicit downstream dependency wiring. An early return from a
`@task` function completes the task successfully with no output — Airflow marks it
green, and the transform group proceeds normally.

`BranchPythonOperator` is the right tool when you want to take genuinely different
downstream paths. Here, there is only one downstream path (transform); the only question
is whether XDC extraction runs. An early return is the right level of complexity.

---

#### Seed hash optimisation

`dbt seed` loads reference CSVs into DuckDB. The seed data rarely changes — running
`dbt seed` on every daily pipeline run is wasted work. The `dbt_seed` task skips the
seed step if the CSV files are unchanged:

```python
def _seeds_hash() -> str:
    """MD5 of all seed CSV files, sorted for stability."""
    seed_dir = Path(DBT_DIR) / "seeds"
    h = hashlib.md5()
    for f in sorted(seed_dir.rglob("*.csv")):
        h.update(f.read_bytes())
    return h.hexdigest()
```

The hash is stored in S3 at `state/seed_hash`. On each run, the task computes the
current hash, compares it to the stored value, and skips if they match. After a
successful seed, the stored hash is updated.

The hash covers all CSV files sorted by path — the sort is essential for stability,
since `rglob` returns files in filesystem order which is not guaranteed to be
consistent across platforms or runs.

Storing state in S3 (rather than Airflow's metadata database or a local file) means the
hash persists across Airflow restarts and is accessible to all workers in a distributed
deployment.

---

#### `_dbt()` — where `run_date` is passed

The `_dbt()` helper runs dbt commands and is the link between the S3 partition strategy
and the Airflow orchestrator:

```python
def _dbt(command: str) -> None:
    run_date = date.today().isoformat()
    result = subprocess.run(
        ["dbt", command, "--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR,
         "--vars", f"{{run_date: {run_date}}}"],
        ...
    )
```

`--vars '{run_date: 2026-04-30}'` injects today's date as a dbt variable. Every staging
model reads `{{ var('run_date') }}` to determine which S3 partition to read. Airflow
determines the date; the staging models consume it. This is why both changes —
date-specific S3 reads and the Airflow DAG — were built in the same session.

---

### XDC deduplication with QUALIFY

`int_xdc_variants.sql` joins the variants staging model to the stock staging model.
Both can contain duplicate rows from partial or retried API extractions. The fix is
`QUALIFY ROW_NUMBER()` applied to each CTE source before the join:

```sql
with variants as (
    select *
    from {{ ref('stg_xdc_variants') }}
    qualify row_number() over (partition by product_id, variant_id order by 1) = 1
),

stock as (
    select *
    from {{ ref('stg_xdc_stock') }}
    qualify row_number() over (partition by variant_id order by 1) = 1
),
```

`QUALIFY` is a DuckDB (and Snowflake/BigQuery) extension that filters rows based on
window function results within the same SELECT — equivalent to wrapping the whole query
in a subquery with a `WHERE rn = 1`, but cleaner. Standard SQL does not have `QUALIFY`.

`ORDER BY 1` (the first column) in a deduplication window is a valid DuckDB idiom when
the intent is "keep one row, any row" — you are not trying to pick the newest or
largest, just eliminate exact duplicates. Once `run_date` is fully wired, the source
will have no duplicates and the QUALIFY becomes defensive rather than load-bearing.

---

## The Changes Made

| File | Change |
|---|---|
| `airflow/dags/supply_integration.py` | New — TaskFlow DAG with extract + transform TaskGroups, seed hash optimisation, XDC conditional skip |
| `airflow/Dockerfile` | New — single-line `FROM astro-runtime:12.0.0` |
| `airflow/docker-compose.override.yml` | New — mounts project root into all Airflow services, injects `.env` credentials |
| `airflow/requirements.txt` | New — pipeline dependencies installed into the Airflow image |
| `airflow/.astro/config.yaml` | New — Astronomer project name and port config |
| `dbt_project/models/staging/stg_mko_*.sql` (×5) | Wildcard `*/` → `{{ var('run_date') }}/` |
| `dbt_project/models/staging/stg_xdc_*.sql` (×6) | Wildcard `*/` → `{{ var('run_date') }}/` |
| `extractor/loader.py` | Added `delete_partition()` function |
| `extractor/mko.py` | Added `_delete_old_partition()` method; call after upload |
| `extractor/xdc.py` | Added `_delete_old_partition()` method; call after upload |
| `dbt_project/models/intermediate/int_xdc_variants.sql` | `QUALIFY` deduplication on variants + stock CTEs |
| `dbt_project/models/marts/schema.yml` | Variants grain description updated; `unique` test removed |
| `dbt_project/tests/test_variants_unique_key.sql` | Test updated to composite key `(supplier, product_ref, variant_id)` |

---

## What I Should Be Able to Explain After Day 10

- Why the glob read (`*/`) caused duplicates and why date-specific reads fix it at the source
- What a dbt `var()` is and how it differs from `env_var()` — who sets each one
- How `delete_partition()` works and why cleanup runs after upload, not before
- Why keeping yesterday's partition (not just today's) is the right retention choice
- What Astronomer Astro is and how `astro dev start` differs from a raw Airflow install
- What the TaskFlow API (`@dag`, `@task`) is and why it is preferred over `PythonOperator`
- What `TaskGroup` does and how `extract_group >> transform_group` sets dependencies
- Why `catchup=False` matters for a pipeline that processes only today's data
- Why XDC is skipped with an early return rather than `BranchPythonOperator`
- How the seed hash optimisation works and why the hash is stored in S3
- How `docker-compose.override.yml` makes the project code available inside Astro containers without copying it
- Why `variant_id` alone is not a unique key in the variants mart
- How `QUALIFY ROW_NUMBER()` works in DuckDB and what it is equivalent to in standard SQL
