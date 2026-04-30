# Day 11 — CI/CD, Airflow Validation, and QUALIFY Investigation

## What I Did

Three pieces of work, completing the project plan:

1. **Created a GitHub Actions CI pipeline** that runs on every push and pull request to `main`.
2. **Validated the Airflow DAG end-to-end** — triggered a manual run and confirmed all five tasks succeeded.
3. **Investigated whether the QUALIFY in `int_mko_variants.sql` could be removed** — it cannot, and the Day 10 hypothesis was wrong.

---

## GitHub Actions CI

`.github/workflows/ci.yml` defines a single job with two steps:

```yaml
- name: Run unit tests
  run: pytest tests/

- name: dbt parse
  env:
    AWS_ACCESS_KEY_ID: dummy
    AWS_SECRET_ACCESS_KEY: dummy
    AWS_DEFAULT_REGION: eu-south-2
  run: dbt parse --project-dir dbt_project --profiles-dir dbt_project
```

**Why dummy AWS credentials for `dbt parse`?** `dbt parse` validates SQL syntax without
connecting to any database. However, the `profiles.yml` references `env_var('AWS_ACCESS_KEY_ID')`
without a default, so dbt raises a parse error if the variable is unset — even though the value
is never used. Passing dummy values satisfies the reference without granting any real access.

The two steps together give fast, credential-free feedback on every push: 28 unit tests covering
all five MKO endpoint parsers, the retry client, and the S3 loader; plus syntactic validation
of all 34 dbt models.

---

## Airflow DAG End-to-End Validation

Astronomer Astro was already running (`astro dev ps` showed all four containers live). I triggered
a manual run and monitored task states:

| Task | Duration | Result |
|---|---|---|
| `extract.extract_mko` | ~12s | success |
| `extract.extract_xdc` | ~34s | success |
| `transform.dbt_seed` | ~4s | success (skipped — seed hash unchanged) |
| `transform.dbt_run` | ~42s | success |
| `transform.dbt_test` | ~14s | success |

Total wall time: ~1m 35s. The seed hash optimisation from Day 10 is working — the CSVs were
unchanged so `dbt seed` was skipped, saving ~30s on each daily run after the first.

---

## QUALIFY Investigation: A Day 10 Correction

Day 10 added date-specific S3 reads (`{{ var('run_date') }}`) to replace the glob pattern
that caused row duplication. The Day 10 notes stated the `QUALIFY ROW_NUMBER()` in
`int_mko_variants.sql` "can be removed once the pipeline is confirmed passing with date-specific
reads" — the assumption being that the duplicates came from multiple date partitions.

This session tested that assumption by removing the QUALIFY and running `dbt test`. The composite
key test (`test_variants_unique_key.sql`) failed with 5 duplicate `(supplier, product_ref, variant_id)`
combinations. I queried the raw S3 Parquet directly to find the cause:

```python
con.execute("""
SELECT product_ref, matnr, count(*) as cnt
FROM read_parquet('s3://.../mko/raw/product/2026-04-30/variants.parquet')
GROUP BY product_ref, matnr
HAVING count(*) > 1
""")
# Returns: 21281/21281002000, 21281/21281006000, 21281/21281117000, 21308/21308002000, 21378/21378002000
```

The duplicates exist in MKO's source data. The QUALIFY is not a workaround for the glob read —
it is the correct fix for genuine source-level duplicates that MKO's API returns for certain
product/variant combinations. The QUALIFY was restored with a comment recording this finding:

```sql
-- MKO source data contains genuine duplicate (product_ref, matnr) rows
qualify row_number() over (partition by v.product_ref, v.matnr order by 1) = 1
```

The Day 10 QUALIFY on `int_xdc_variants.sql` is separately defensive against XDC extract
retries and is unaffected.

---

## The Changes Made

| File | Change |
|---|---|
| `.github/workflows/ci.yml` | New — pytest + dbt parse on push/PR to main |
| `dbt_project/models/intermediate/int_mko_variants.sql` | QUALIFY comment updated to document real cause (source duplicates, not glob reads) |

---

## What I Should Be Able to Explain After Day 11

- Why `dbt parse` needs dummy AWS credentials even though it does not connect
- What the two CI steps validate and what they do not (they do not test against real S3 or run dbt models)
- Why the seed hash optimisation is visible in the Airflow UI as a fast, green `dbt_seed` task
- Why the QUALIFY in `int_mko_variants.sql` is load-bearing and cannot be removed with date-specific reads alone
- How to confirm the source of duplicates — query the raw Parquet directly rather than inferring from the dbt layer
