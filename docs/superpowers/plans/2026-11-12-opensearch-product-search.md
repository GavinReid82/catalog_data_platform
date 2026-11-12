# OpenSearch Product Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add product search to `catalog_data_platform`. Load the dbt `catalog` table into OpenSearch, search it three ways (BM25 keyword, vector, hybrid), and measure which way finds the right products, using a judged query set and nDCG@10, MRR@10 and Recall@10.

**Architecture:** A new `search/` package reads the `catalog` mart from DuckDB, turns each row into a search document, embeds it with a small local sentence-transformers model, and bulk-loads it into a single-node OpenSearch running in Docker. Query builders are pure functions that return OpenSearch request bodies, so they unit-test without a server. Hybrid search uses an OpenSearch search pipeline with the `normalization-processor` (min-max normalisation, weighted arithmetic mean). An `evaluate` CLI runs every judged query through every method and writes a results JSON plus a Markdown table. The Airflow DAG gets one new task, `index_search`, after `dbt_test`.

**Tech Stack:** OpenSearch 2.17.1 (Docker), opensearch-py 2.7.1, sentence-transformers 3.2.1 (`all-MiniLM-L6-v2`, 384 dims), DuckDB 1.1.3, PyYAML 6.0.2, pytest 8.3.5, Airflow (Astronomer runtime 12.0.0).

**Spec:** No separate spec file. The design was agreed in chat on 2026-11-12. Why this project: two live leads (Apiux → Ayesa, DIGITAL55) ask for Airflow + OpenSearch + BM25 + "statistics to tune relevance", and OpenSearch is the biggest gap in the portfolio.

## Global Constraints

- Repo: `~/code_projects/catalog_data_platform`. Work on branch `feature/opensearch-search`, never on `main`.
- Do NOT stage or commit `tests/extractor/test_vta.py`. It has an unrelated uncommitted edit. Always `git add` explicit paths, never `git add -A` or `git add .`.
- Python 3.11. Pin every new dependency to an exact version.
- OpenSearch image: `opensearchproject/opensearch:2.17.1`, single node, security plugin off (local only).
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`, dimension 384. If Task 0 shows the product text is mostly Spanish, switch to `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (also 384) and set `ANALYZER = "spanish"`. Decide once, in Task 0.
- Document id: `"{supplier}:{product_ref}"`, for example `"vta:12345"`.
- `sentence-transformers` (it pulls in torch, which is huge) must never be imported at module top level outside `search/embed.py`. CI does not install it.
- Honesty rules for every README line, case study and CV line that comes out of this:
  - Every number must come from a committed file in `search/eval/results/`. No number before Task 8 has run.
  - Say plainly that one person (Gavin) wrote and graded the queries, and say how many.
  - Never call it "production". It is a local Docker setup.
  - Supplier names stay fictional (Vantora / Kestrel). No HelloPrint names, code or data identifiers.
  - Tuned numbers (Task 9) are in-sample: they were tuned on the same queries they are scored on. Say so, or quote the baseline numbers for the method comparison.
- Learning rule (Gavin): before each task, say in one plain sentence what it does and why. Before running a test, predict the result, then run it and paste the real output.

## File Map

| File | Job |
|---|---|
| `docker-compose.yml` (modify) | Add the `opensearch` service and a volume. |
| `requirements.txt` (modify) | Add `opensearch-py`, `pyyaml`. |
| `requirements-embed.txt` (create) | `sentence-transformers` only. Kept apart so CI stays light. |
| `search/__init__.py` | Empty package marker. |
| `search/documents.py` | DuckDB `catalog` rows → search documents. |
| `search/metrics.py` | nDCG@k, MRR@k, Recall@k. Pure Python. |
| `search/queries.py` | Build BM25, kNN and hybrid request bodies. Pure. |
| `search/index.py` | OpenSearch client, index mapping, bulk load, hybrid pipeline. |
| `search/embed.py` | The only place that imports sentence-transformers. |
| `search/pipeline.py` | `run_indexing()`: DuckDB → embeddings → OpenSearch. |
| `search/runner.py` | Run one query with one method; pool candidates for grading. |
| `search/pool.py` | CLI: show pooled candidates for a query so Gavin can grade them. |
| `search/evaluate.py` | CLI: run all judged queries, compute metrics, write results. |
| `search/eval/judgements.yaml` | The judged queries (written by Gavin in Task 7). |
| `search/eval/results/*.json` | One file per evaluation run. Committed. |
| `tests/search/...` | Unit tests + one integration test file (skips without OpenSearch). |
| `airflow/dags/supply_integration.py` (modify) | New `index_search` task after `dbt_test`. |
| `airflow/docker-compose.override.yml`, `airflow/requirements.txt` (modify) | OpenSearch for the Airflow containers. |
| `.github/workflows/ci.yml` (modify) | Run the new unit tests. |
| `README.md` (modify) | Search section with the real results table. |

---

### Task 0: Branch, environment, and real catalogue data (GATE)

> **DONE 2026-11-12.** Live feeds need a supplier account code we do not have, so the pipeline was rebuilt from saved S3 data: run dbt with `export KES_BASE_URL=offline-replay` and `--vars '{run_date: 2026-06-09}'`. Catalog = 4,479 vta + 1,382 kes = 5,861 products, English. Fixed `int_kes_variants` (`threshold_quantity`) and added `description` + `keywords` to `catalog` (Vantora names are model names like "Kolka", so search needs them). dbt test 27/29: 2 null print prices in the source data. Skip to Task 1.

**Why:** Search needs products to search. Right now `data/` does not exist and there is no `.env`, so the pipeline has never run on this machine. Without real data, Tasks 7–9 cannot happen. This task also gives the project its first proof of an end-to-end run.

**Files:** none committed except notes in Step 6.

- [ ] **Step 1: Make the branch**

```bash
cd ~/code_projects/catalog_data_platform
git switch -c feature/opensearch-search
```

- [ ] **Step 2: Make the virtual environment**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -q
```

Expected: `28 passed` (the existing extractor tests).

- [ ] **Step 3: Create `.env`** with the real values (never commit it; it is already in `.gitignore`):

```
S3_BUCKET=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=eu-south-2
VTA_BASE_URL=...
VTA_URL_SUFFIX_PRODUCT=...
VTA_URL_SUFFIX_PRICE=...
VTA_URL_SUFFIX_STOCK=...
VTA_URL_SUFFIX_PRINT=...
VTA_URL_SUFFIX_PRINT_PRICE=...
DUCKDB_PATH=data/catalog_data_platform.duckdb
```

**STOP HERE if the supplier feed URLs or the S3 bucket are not available.** Do not invent product data. Go back to Gavin and choose a different data source.

- [ ] **Step 4: Run the pipeline end to end**

```bash
mkdir -p data
python run_pipeline.py 2>&1 | tee data/first_run.log
```

Expected: ends with `dbt test` passing and no traceback.

- [ ] **Step 5: Check the catalogue**

```bash
python -c "
import duckdb
con = duckdb.connect('data/catalog_data_platform.duckdb', read_only=True)
print(con.execute('select supplier, count(*) from catalog group by 1').fetchall())
for r in con.execute('select product_name, category, subcategory, composition from catalog using sample 8').fetchall():
    print(r)
"
```

Expected: one row count per supplier (more than 100 products, or the evaluation will be weak), then 8 sample products.

- [ ] **Step 6: Decide the language**

Read the 8 samples. If the names are mostly English, keep the defaults. If mostly Spanish, use the multilingual model and `ANALYZER = "spanish"` everywhere below. Write the product count, the date, and the language choice in a scratch note for the README (Task 11).

---

### Task 1: OpenSearch in Docker

**Why:** OpenSearch is the search engine. Running it in Docker means anyone can start it with one command.

**Files:**
- Modify: `docker-compose.yml`
- Modify: `requirements.txt`
- Create: `requirements-embed.txt`

- [ ] **Step 1: Add the service.** In `docker-compose.yml`, add under `services:` (same indent as `pipeline:`):

```yaml
  opensearch:
    image: opensearchproject/opensearch:2.17.1
    environment:
      - discovery.type=single-node
      - DISABLE_SECURITY_PLUGIN=true
      - DISABLE_INSTALL_DEMO_CONFIG=true
      - OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m
    ports:
      - "9200:9200"
    volumes:
      - opensearch-data:/usr/share/opensearch/data
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:9200/_cluster/health || exit 1"]
      interval: 10s
      retries: 12
```

And at the bottom of the file, at top level:

```yaml
volumes:
  opensearch-data:
```

- [ ] **Step 2: Start it and check it**

```bash
docker compose up -d opensearch
curl -s localhost:9200 | grep '"number"'
curl -s localhost:9200/_cat/plugins | grep -E "neural-search|knn"
```

Expected: `"number" : "2.17.1"`, then two plugin lines: `opensearch-knn` and `opensearch-neural-search`. Hybrid search needs both.

- [ ] **Step 3: Dependencies.** Append to `requirements.txt`:

```
opensearch-py==2.7.1
pyyaml==6.0.2
```

Create `requirements-embed.txt`:

```
sentence-transformers==3.2.1
```

```bash
pip install -r requirements.txt -r requirements-embed.txt
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml requirements.txt requirements-embed.txt
git commit -m "feat(search): add single-node OpenSearch service and search dependencies"
```

---

### Task 2: Catalogue rows → search documents

**Why:** OpenSearch stores JSON documents, not table rows. This turns one product row into one document and builds a `search_text` field that is used for embeddings.

**Files:**
- Create: `search/__init__.py` (empty), `tests/search/__init__.py` (empty)
- Create: `search/documents.py`
- Test: `tests/search/test_documents.py`

**Interfaces:**
- Produces: `TEXT_FIELDS: tuple[str, ...]`, `doc_id(supplier: str, product_ref: str) -> str`, `row_to_doc(row: dict) -> dict`, `load_catalog(db_path: str) -> list[dict]`. Every document has keys `id`, `supplier`, `product_ref`, every name in `TEXT_FIELDS`, `min_unit_price`, `in_stock_now`, `search_text`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/search/test_documents.py
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
```

- [ ] **Step 2: Run it, expect failure**

Run: `pytest tests/search/test_documents.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'search.documents'`.

- [ ] **Step 3: Write the code**

```python
# search/documents.py
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
```

Note: `order by supplier desc` puts `vta` before `kes`, so the test order is stable.

- [ ] **Step 4: Run it, expect pass**

Run: `pytest tests/search/test_documents.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add search/__init__.py search/documents.py tests/search/__init__.py tests/search/test_documents.py
git commit -m "feat(search): map catalog rows to search documents"
```

---

### Task 3: Relevance metrics

**Why:** These are the three scores that say "did the right products come near the top?". You will be asked to explain them in an interview, so the tests use numbers you can work out by hand.

- **Recall@10:** of all the right products, how many are in the top 10.
- **MRR@10:** 1 ÷ the position of the first right product (1st → 1.0, 2nd → 0.5, none → 0).
- **nDCG@10:** rewards very relevant products near the top. Each hit is worth `grade ÷ log2(position + 1)`, then divided by the best possible score, so 1.0 = perfect order.

**Files:**
- Create: `search/metrics.py`
- Test: `tests/search/test_metrics.py`

**Interfaces:**
- Produces: `ndcg_at_k(ranked: list[str], grades: dict[str, int], k: int = 10) -> float`, `mrr_at_k(...) -> float`, `recall_at_k(...) -> float`. Same arguments for all three. A grade above 0 counts as relevant.

- [ ] **Step 1: Write the failing tests**

```python
# tests/search/test_metrics.py
import math

import pytest

from search.metrics import mrr_at_k, ndcg_at_k, recall_at_k

GRADES = {"a": 3, "c": 2}


def test_perfect_order_scores_one():
    assert ndcg_at_k(["a", "c", "x"], GRADES) == pytest.approx(1.0)


def test_ndcg_hand_worked():
    # ranked a, x, c → 3/log2(2) + 0 + 2/log2(4) = 3 + 1 = 4
    # ideal  a, c    → 3/log2(2) + 2/log2(3)     = 3 + 1.26186 = 4.26186
    assert ndcg_at_k(["a", "x", "c"], GRADES) == pytest.approx(4 / (3 + 2 / math.log2(3)))


def test_ndcg_nothing_relevant_found():
    assert ndcg_at_k(["x", "y"], GRADES) == 0.0


def test_ndcg_respects_k():
    assert ndcg_at_k(["x", "a"], GRADES, k=1) == 0.0


def test_mrr_first_hit_at_position_two():
    assert mrr_at_k(["x", "c", "a"], GRADES) == pytest.approx(0.5)


def test_mrr_no_hit():
    assert mrr_at_k(["x", "y"], GRADES) == 0.0


def test_recall_half_found():
    assert recall_at_k(["a", "x"], GRADES) == pytest.approx(0.5)


def test_zero_grade_is_not_relevant():
    assert recall_at_k(["a"], {"a": 0, "b": 1}) == 0.0


def test_empty_grades_score_zero():
    assert ndcg_at_k(["a"], {}) == 0.0
    assert recall_at_k(["a"], {}) == 0.0
```

- [ ] **Step 2: Run it, expect failure**

Run: `pytest tests/search/test_metrics.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'search.metrics'`.

- [ ] **Step 3: Write the code**

```python
# search/metrics.py
"""Ranking metrics. `ranked` is the result list, best first. `grades` maps doc id → 0–3."""
import math


def _dcg(gains: list[int]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranked: list[str], grades: dict[str, int], k: int = 10) -> float:
    ideal = _dcg(sorted(grades.values(), reverse=True)[:k])
    if ideal == 0:
        return 0.0
    return _dcg([grades.get(d, 0) for d in ranked[:k]]) / ideal


def mrr_at_k(ranked: list[str], grades: dict[str, int], k: int = 10) -> float:
    for position, d in enumerate(ranked[:k], start=1):
        if grades.get(d, 0) > 0:
            return 1 / position
    return 0.0


def recall_at_k(ranked: list[str], grades: dict[str, int], k: int = 10) -> float:
    relevant = {d for d, g in grades.items() if g > 0}
    if not relevant:
        return 0.0
    return len(relevant & set(ranked[:k])) / len(relevant)
```

- [ ] **Step 4: Run it, expect pass**

Run: `pytest tests/search/test_metrics.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add search/metrics.py tests/search/test_metrics.py
git commit -m "feat(search): add nDCG, MRR and recall at k"
```

---

### Task 4: Query builders

**Why:** Each search method is just a different JSON request to OpenSearch. Building them as plain functions means we can test them with no server running.

- **BM25:** keyword match. `product_name^3` means a match in the name counts 3× more than a match in `brand`.
- **kNN (vector):** find the products whose embedding is closest to the query's embedding. Good for "something to keep coffee hot".
- **Hybrid:** run both, then the search pipeline (Task 5) rescales both score lists to 0–1 and blends them.

**Files:**
- Create: `search/queries.py`
- Test: `tests/search/test_queries.py`

**Interfaces:**
- Produces: `DEFAULT_BM25_FIELDS: list[str]`, `bm25_query(text: str, size: int = 10, fields: list[str] | None = None) -> dict`, `knn_query(vector: list[float], size: int = 10) -> dict`, `hybrid_query(text: str, vector: list[float], size: int = 10, fields: list[str] | None = None) -> dict`. The vector field is named `"embedding"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/search/test_queries.py
from search.queries import DEFAULT_BM25_FIELDS, bm25_query, hybrid_query, knn_query


def test_bm25_uses_default_boosted_fields():
    body = bm25_query("steel bottle", size=5)
    assert body["size"] == 5
    mm = body["query"]["multi_match"]
    assert mm["query"] == "steel bottle"
    assert mm["fields"] == DEFAULT_BM25_FIELDS
    assert "product_name^3" in DEFAULT_BM25_FIELDS


def test_bm25_custom_fields():
    body = bm25_query("x", fields=["product_name"])
    assert body["query"]["multi_match"]["fields"] == ["product_name"]


def test_knn_targets_embedding_field():
    body = knn_query([0.1, 0.2], size=7)
    assert body["query"]["knn"]["embedding"] == {"vector": [0.1, 0.2], "k": 7}
    assert body["size"] == 7


def test_hybrid_contains_bm25_then_knn():
    body = hybrid_query("bottle", [0.1, 0.2], size=10)
    subqueries = body["query"]["hybrid"]["queries"]
    assert list(subqueries[0]) == ["multi_match"]
    assert list(subqueries[1]) == ["knn"]
```

- [ ] **Step 2: Run it, expect failure**

Run: `pytest tests/search/test_queries.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Write the code**

```python
# search/queries.py
"""OpenSearch request bodies for the three search methods."""

DEFAULT_BM25_FIELDS = [
    "product_name^3",
    "product_type^2",
    "category^2",
    "subcategory^2",
    "keywords^2",
    "brand",
    "composition",
    "description",
]


def _multi_match(text: str, fields: list[str] | None) -> dict:
    return {"multi_match": {"query": text, "fields": fields or DEFAULT_BM25_FIELDS,
                            "type": "best_fields"}}


def _knn(vector: list[float], k: int) -> dict:
    return {"knn": {"embedding": {"vector": vector, "k": k}}}


def bm25_query(text: str, size: int = 10, fields: list[str] | None = None) -> dict:
    return {"size": size, "query": _multi_match(text, fields)}


def knn_query(vector: list[float], size: int = 10) -> dict:
    return {"size": size, "query": _knn(vector, size)}


def hybrid_query(text: str, vector: list[float], size: int = 10,
                 fields: list[str] | None = None) -> dict:
    # Order matters: the pipeline weights apply to these sub-queries in this order.
    return {"size": size,
            "query": {"hybrid": {"queries": [_multi_match(text, fields), _knn(vector, size)]}}}
```

- [ ] **Step 4: Run it, expect pass**

Run: `pytest tests/search/test_queries.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add search/queries.py tests/search/test_queries.py
git commit -m "feat(search): add BM25, kNN and hybrid query builders"
```

---

### Task 5: Index, embeddings and the indexing pipeline

**Why:** This creates the OpenSearch index (the mapping says which fields are text and which is the vector), embeds every product, loads them, and sets up the hybrid search pipeline. After this task, real searches work.

**Files:**
- Create: `search/index.py`, `search/embed.py`, `search/pipeline.py`
- Test: `tests/search/test_index.py` (unit), `tests/search/test_opensearch_integration.py` (needs OpenSearch)

**Interfaces:**
- Consumes: `load_catalog` (Task 2), `bm25_query`, `hybrid_query` (Task 4).
- Produces:
  - `search/index.py`: `INDEX_NAME = "products"`, `PIPELINE_NAME = "hybrid-minmax"`, `ANALYZER = "english"`, `get_client(url: str | None = None) -> OpenSearch`, `index_body(dim: int) -> dict`, `recreate_index(client, name: str, dim: int) -> None`, `bulk_index(client, name: str, docs: list[dict], vectors: list[list[float]]) -> int`, `ensure_hybrid_pipeline(client, name: str = PIPELINE_NAME, weights: tuple[float, float] = (0.5, 0.5)) -> None`.
  - `search/embed.py`: `MODEL_NAME`, `DIM = 384`, class `Embedder` with attribute `dim: int` and method `embed(texts: list[str]) -> list[list[float]]`.
  - `search/pipeline.py`: `run_indexing(db_path: str, client, embedder, index: str = INDEX_NAME) -> int` (returns number of documents indexed).
  - Any object with `.dim` and `.embed(texts)` works as an embedder. Tests use a fake one.

- [ ] **Step 1: Write the failing unit test**

```python
# tests/search/test_index.py
from search.index import ANALYZER, index_body


def test_index_body_has_vector_field_with_right_dimension():
    body = index_body(dim=384)
    emb = body["mappings"]["properties"]["embedding"]
    assert emb["type"] == "knn_vector"
    assert emb["dimension"] == 384
    assert emb["method"]["space_type"] == "cosinesimil"
    assert body["settings"]["index"]["knn"] is True


def test_text_fields_use_the_language_analyzer():
    props = index_body(dim=4)["mappings"]["properties"]
    assert props["product_name"] == {"type": "text", "analyzer": ANALYZER}
    assert props["supplier"] == {"type": "keyword"}
```

- [ ] **Step 2: Run it, expect failure**

Run: `pytest tests/search/test_index.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Write `search/index.py`**

```python
# search/index.py
"""OpenSearch index setup and loading."""
import os

from opensearchpy import OpenSearch, helpers

from search.documents import TEXT_FIELDS

INDEX_NAME = "products"
PIPELINE_NAME = "hybrid-minmax"
ANALYZER = "english"  # Task 0 may change this to "spanish"


def get_client(url: str | None = None) -> OpenSearch:
    url = url or os.getenv("OPENSEARCH_URL", "http://localhost:9200")
    return OpenSearch(hosts=[url], use_ssl=False, verify_certs=False, timeout=60)


def index_body(dim: int) -> dict:
    text = {"type": "text", "analyzer": ANALYZER}
    properties = {field: dict(text) for field in TEXT_FIELDS}
    properties.update({
        "search_text": dict(text),
        "supplier": {"type": "keyword"},
        "product_ref": {"type": "keyword"},
        "min_unit_price": {"type": "float"},
        "in_stock_now": {"type": "boolean"},
        "embedding": {
            "type": "knn_vector",
            "dimension": dim,
            "method": {"name": "hnsw", "engine": "lucene", "space_type": "cosinesimil"},
        },
    })
    return {
        "settings": {"index": {"knn": True, "number_of_shards": 1, "number_of_replicas": 0}},
        "mappings": {"properties": properties},
    }


def recreate_index(client: OpenSearch, name: str, dim: int) -> None:
    if client.indices.exists(index=name):
        client.indices.delete(index=name)
    client.indices.create(index=name, body=index_body(dim))


def bulk_index(client: OpenSearch, name: str, docs: list[dict], vectors: list[list[float]]) -> int:
    actions = (
        {"_index": name, "_id": doc["id"],
         "_source": {**{k: v for k, v in doc.items() if k != "id"}, "embedding": vec}}
        for doc, vec in zip(docs, vectors, strict=True)
    )
    ok, _ = helpers.bulk(client, actions, raise_on_error=True)
    client.indices.refresh(index=name)
    return ok


def ensure_hybrid_pipeline(client: OpenSearch, name: str = PIPELINE_NAME,
                           weights: tuple[float, float] = (0.5, 0.5)) -> None:
    """Min-max scale BM25 and kNN scores to 0–1, then take a weighted mean (BM25, kNN)."""
    body = {
        "description": "Hybrid BM25 + kNN",
        "phase_results_processors": [{
            "normalization-processor": {
                "normalization": {"technique": "min_max"},
                "combination": {"technique": "arithmetic_mean",
                                "parameters": {"weights": list(weights)}},
            }
        }],
    }
    client.transport.perform_request("PUT", f"/_search/pipeline/{name}", body=body)
```

- [ ] **Step 4: Run the unit test, expect pass**

Run: `pytest tests/search/test_index.py -v`
Expected: 2 passed.

- [ ] **Step 5: Write `search/embed.py` and `search/pipeline.py`**

```python
# search/embed.py
"""The only module that imports sentence-transformers (it pulls in torch)."""
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # Task 0 may switch to the multilingual model
DIM = 384


class Embedder:
    dim = DIM

    def __init__(self, model_name: str = MODEL_NAME):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, batch_size=64, normalize_embeddings=True).tolist()
```

```python
# search/pipeline.py
"""DuckDB catalog → embeddings → OpenSearch."""
import logging

from search.documents import load_catalog
from search.index import INDEX_NAME, bulk_index, ensure_hybrid_pipeline, recreate_index

log = logging.getLogger(__name__)


def run_indexing(db_path: str, client, embedder, index: str = INDEX_NAME) -> int:
    docs = load_catalog(db_path)
    log.info("Loaded %d products from %s", len(docs), db_path)
    vectors = embedder.embed([d["search_text"] for d in docs])
    recreate_index(client, index, embedder.dim)
    count = bulk_index(client, index, docs, vectors)
    ensure_hybrid_pipeline(client)
    log.info("Indexed %d documents into %s", count, index)
    return count
```

- [ ] **Step 6: Write the integration test** (uses a fake 4-dimension embedder so it is fast and needs no torch)

```python
# tests/search/test_opensearch_integration.py
import os

import duckdb
import pytest

pytestmark = pytest.mark.skipif(not os.getenv("OPENSEARCH_URL"),
                                reason="needs a running OpenSearch (set OPENSEARCH_URL)")

from search.index import PIPELINE_NAME, get_client  # noqa: E402
from search.pipeline import run_indexing  # noqa: E402
from search.queries import bm25_query, hybrid_query  # noqa: E402

TEST_INDEX = "products_test"
WORDS = ["bottle", "bag", "pen", "mug"]


class FakeEmbedder:
    dim = 4

    def embed(self, texts):
        return [[1.0 if w in t.lower() else 0.01 for w in WORDS] for t in texts]


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "t.duckdb")
    con = duckdb.connect(path)
    con.execute("""
        create table catalog as select * from (values
          ('vta', 'A1', 'Steel water bottle', 'Drinkware'),
          ('vta', 'A2', 'Cotton tote bag', 'Bags'),
          ('vta', 'A3', 'Ballpoint pen', 'Writing')
        ) t(supplier, product_ref, product_name, category)
    """)
    con.close()
    return path


def test_index_then_search(db):
    client = get_client()
    assert run_indexing(db, client, FakeEmbedder(), index=TEST_INDEX) == 3

    hits = client.search(index=TEST_INDEX, body=bm25_query("bottle"))["hits"]["hits"]
    assert hits[0]["_id"] == "vta:A1"

    body = hybrid_query("bag", FakeEmbedder().embed(["bag"])[0])
    resp = client.transport.perform_request(
        "POST", f"/{TEST_INDEX}/_search", params={"search_pipeline": PIPELINE_NAME}, body=body)
    assert resp["hits"]["hits"][0]["_id"] == "vta:A2"

    client.indices.delete(index=TEST_INDEX)
```

- [ ] **Step 7: Run it against the real OpenSearch**

Predict first: which id comes back first for "bottle"? For "bag"?

```bash
docker compose up -d opensearch
OPENSEARCH_URL=http://localhost:9200 pytest tests/search/ -v
```

Expected: all search tests pass, including `test_index_then_search` (not skipped).

- [ ] **Step 8: Index the real catalogue**

```bash
python -c "
import logging; logging.basicConfig(level=logging.INFO)
from search.embed import Embedder
from search.index import get_client
from search.pipeline import run_indexing
print(run_indexing('data/catalog_data_platform.duckdb', get_client(), Embedder()))
"
curl -s 'localhost:9200/products/_count'
```

Expected: the printed count equals the catalogue count from Task 0 Step 5, and `_count` shows the same number.

- [ ] **Step 9: Commit**

```bash
git add search/index.py search/embed.py search/pipeline.py tests/search/test_index.py tests/search/test_opensearch_integration.py
git commit -m "feat(search): index catalog into OpenSearch with embeddings and hybrid pipeline"
```

---

### Task 6: Search runner and the pooling tool

**Why:** One function runs any method on any query. The pool tool shows the top 10 from all three methods merged together, so you only grade products that some method actually found. This is called **pooling**. It is how TREC, the big search evaluation competitions, build their judgements, and it is a good interview point.

**Files:**
- Create: `search/runner.py`, `search/pool.py`
- Test: `tests/search/test_runner.py`

**Interfaces:**
- Consumes: `bm25_query`, `knn_query`, `hybrid_query` (Task 4); `INDEX_NAME`, `PIPELINE_NAME`, `get_client` (Task 5); `Embedder` (Task 5).
- Produces: `METHODS = ("bm25", "vector", "hybrid")`, `run_search(client, embedder, method: str, text: str, size: int = 10, index: str = INDEX_NAME, fields: list[str] | None = None, pipeline: str = PIPELINE_NAME) -> list[str]` (doc ids, best first), `pool_candidates(client, embedder, text: str, depth: int = 10, index: str = INDEX_NAME) -> list[str]` (unique ids, first-seen order).

- [ ] **Step 1: Write the failing tests** (a fake client records what it was asked)

```python
# tests/search/test_runner.py
import pytest

from search.runner import pool_candidates, run_search


class FakeEmbedder:
    dim = 2

    def embed(self, texts):
        return [[0.5, 0.5] for _ in texts]


class FakeTransport:
    def __init__(self, ids):
        self.ids, self.calls = ids, []

    def perform_request(self, method, url, params=None, body=None):
        self.calls.append((method, url, params, body))
        return {"hits": {"hits": [{"_id": i} for i in self.ids]}}


class FakeClient:
    def __init__(self, ids_by_kind):
        self.ids_by_kind = ids_by_kind
        self.transport = FakeTransport(ids_by_kind["hybrid"])

    def search(self, index, body):
        kind = "bm25" if "multi_match" in body["query"] else "vector"
        return {"hits": {"hits": [{"_id": i} for i in self.ids_by_kind[kind]]}}


IDS = {"bm25": ["a", "b"], "vector": ["c", "a"], "hybrid": ["a", "c"]}


@pytest.mark.parametrize("method", ["bm25", "vector", "hybrid"])
def test_run_search_returns_ids_for_each_method(method):
    assert run_search(FakeClient(IDS), FakeEmbedder(), method, "x") == IDS[method]


def test_hybrid_goes_through_the_search_pipeline():
    client = FakeClient(IDS)
    run_search(client, FakeEmbedder(), "hybrid", "x", pipeline="p1")
    method, url, params, _ = client.transport.calls[0]
    assert (method, params) == ("POST", {"search_pipeline": "p1"})
    assert url.endswith("/_search")


def test_unknown_method_raises():
    with pytest.raises(ValueError):
        run_search(FakeClient(IDS), FakeEmbedder(), "magic", "x")


def test_pool_is_unique_in_first_seen_order():
    assert pool_candidates(FakeClient(IDS), FakeEmbedder(), "x") == ["a", "b", "c"]
```

- [ ] **Step 2: Run it, expect failure**

Run: `pytest tests/search/test_runner.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Write `search/runner.py`**

```python
# search/runner.py
"""Run one query with one search method."""
from search.index import INDEX_NAME, PIPELINE_NAME
from search.queries import bm25_query, hybrid_query, knn_query

METHODS = ("bm25", "vector", "hybrid")


def run_search(client, embedder, method: str, text: str, size: int = 10,
               index: str = INDEX_NAME, fields: list[str] | None = None,
               pipeline: str = PIPELINE_NAME) -> list[str]:
    if method == "bm25":
        resp = client.search(index=index, body=bm25_query(text, size, fields))
    elif method == "vector":
        resp = client.search(index=index, body=knn_query(embedder.embed([text])[0], size))
    elif method == "hybrid":
        body = hybrid_query(text, embedder.embed([text])[0], size, fields)
        resp = client.transport.perform_request(
            "POST", f"/{index}/_search", params={"search_pipeline": pipeline}, body=body)
    else:
        raise ValueError(f"unknown method {method!r}; use one of {METHODS}")
    return [hit["_id"] for hit in resp["hits"]["hits"]]


def pool_candidates(client, embedder, text: str, depth: int = 10,
                    index: str = INDEX_NAME) -> list[str]:
    seen: dict[str, None] = {}
    for method in METHODS:
        for doc_id in run_search(client, embedder, method, text, size=depth, index=index):
            seen.setdefault(doc_id)
    return list(seen)
```

- [ ] **Step 4: Run it, expect pass**

Run: `pytest tests/search/test_runner.py -v`
Expected: 6 passed.

- [ ] **Step 5: Write `search/pool.py`**

```python
# search/pool.py
"""Print the pooled top-10 candidates for a query, ready to grade.

Usage: python -m search.pool "insulated coffee cup"
"""
import sys

from search.embed import Embedder
from search.index import INDEX_NAME, get_client
from search.runner import pool_candidates


def main(text: str) -> None:
    client = get_client()
    ids = pool_candidates(client, Embedder(), text)
    docs = client.mget(index=INDEX_NAME, body={"ids": ids})["docs"]
    print(f"# {text}  ({len(ids)} candidates)")
    for d in docs:
        s = d["_source"]
        print(f'      "{d["_id"]}": 0   # {s["product_name"]} | {s["category"]} / {s["subcategory"]}')


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]))
```

- [ ] **Step 6: Try it on the real index**

```bash
python -m search.pool "water bottle"
```

Expected: up to 30 lines (usually fewer, because methods overlap), each already in YAML form with a grade of `0` to change.

- [ ] **Step 7: Commit**

```bash
git add search/runner.py search/pool.py tests/search/test_runner.py
git commit -m "feat(search): add search runner and pooling tool for grading"
```

---

### Task 7: Write the judged queries (Gavin does this by hand)

**Why:** The metrics need an answer key. This is the slow, human part, and it is where the result's honesty comes from. No AI grading: you grade.

**Files:**
- Create: `search/eval/judgements.yaml`

- [ ] **Step 1: Pick 40 queries in three kinds.** Look at real product names and categories first (Task 0 Step 5 sample, or `python -m search.pool` output).
  - 15 **keyword**: words that appear in product names. Example: `"steel water bottle"`.
  - 15 **descriptive**: the need, not the product words. Example: `"something to keep coffee hot"`.
  - 10 **messy**: typos, plurals, odd word order. Example: `"botle insulted"`.

  Prediction to write down now, before any results: which method wins each kind?

- [ ] **Step 2: Grade with this scale** (write it at the top of the file so it is never forgotten):

```yaml
# Grades: 3 = exactly what the query asks for
#         2 = a good substitute
#         1 = related, but a buyer would not pick it
#         0 = wrong
# Graded by one person (Gavin Reid), using pooled top-10 candidates from BM25, vector and hybrid.
queries:
  - id: q01
    type: keyword
    text: "steel water bottle"
    grades:
      "vta:12345": 3
      "vta:67890": 2
```

- [ ] **Step 3: For each query,** run `python -m search.pool "<query>"`, paste the lines under `grades:`, change each `0` to the right grade. Keep the 0 lines: they record that a product was judged wrong, which is different from never judged.

- [ ] **Step 4: Check the file loads and every query has at least one relevant product**

```bash
python -c "
import yaml
q = yaml.safe_load(open('search/eval/judgements.yaml'))['queries']
print(len(q), 'queries')
bad = [x['id'] for x in q if not any(g > 0 for g in x['grades'].values())]
print('no relevant product:', bad)
from collections import Counter; print(Counter(x['type'] for x in q))
"
```

Expected: `40 queries`, `no relevant product: []`, and the three type counts.

- [ ] **Step 5: Commit**

```bash
git add search/eval/judgements.yaml
git commit -m "feat(search): add 40 hand-graded relevance judgements"
```

---

### Task 8: The evaluation CLI and the first real results

**Why:** This turns the answer key into numbers. These numbers are what go on the CV, so they must come from a committed file.

**Files:**
- Create: `search/evaluate.py`
- Test: `tests/search/test_evaluate.py`
- Create (by running): `search/eval/results/<date>-baseline.json`

**Interfaces:**
- Consumes: `METHODS`, `run_search` (Task 6); `ndcg_at_k`, `mrr_at_k`, `recall_at_k` (Task 3); `ensure_hybrid_pipeline`, `get_client` (Task 5).
- Produces: `load_judgements(path: str) -> list[dict]`, `evaluate(search_fn, judgements: list[dict], methods=METHODS, k: int = 10) -> dict`, `to_markdown(results: dict) -> str`. `search_fn(method: str, text: str) -> list[str]`. The results dict looks like `{"bm25": {"overall": {"ndcg": float, "mrr": float, "recall": float}, "by_type": {"keyword": {...}, ...}, "per_query": {"q01": {...}}}, ...}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/search/test_evaluate.py
import pytest

from search.evaluate import evaluate, to_markdown

JUDGEMENTS = [
    {"id": "q1", "type": "keyword", "text": "bottle", "grades": {"a": 3}},
    {"id": "q2", "type": "descriptive", "text": "keep coffee hot", "grades": {"b": 3}},
]

RESULTS = {
    ("bm25", "bottle"): ["a"],
    ("bm25", "keep coffee hot"): ["x"],
    ("vector", "bottle"): ["x", "a"],
    ("vector", "keep coffee hot"): ["b"],
}


def fake_search(method, text):
    return RESULTS[(method, text)]


def test_per_query_and_overall():
    r = evaluate(fake_search, JUDGEMENTS, methods=("bm25", "vector"))
    assert r["bm25"]["per_query"]["q1"]["mrr"] == 1.0
    assert r["bm25"]["per_query"]["q2"]["mrr"] == 0.0
    assert r["bm25"]["overall"]["mrr"] == pytest.approx(0.5)
    assert r["vector"]["overall"]["mrr"] == pytest.approx(0.75)


def test_by_type_split():
    r = evaluate(fake_search, JUDGEMENTS, methods=("bm25", "vector"))
    assert r["bm25"]["by_type"]["keyword"]["recall"] == 1.0
    assert r["bm25"]["by_type"]["descriptive"]["recall"] == 0.0


def test_markdown_has_one_row_per_method():
    md = to_markdown(evaluate(fake_search, JUDGEMENTS, methods=("bm25", "vector")))
    assert "| bm25 |" in md and "| vector |" in md
```

- [ ] **Step 2: Run it, expect failure**

Run: `pytest tests/search/test_evaluate.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Write the code**

```python
# search/evaluate.py
"""Run every judged query through every method and score it.

Usage:
  python -m search.evaluate --label baseline
  python -m search.evaluate --label boosts-name5 --bm25-fields "product_name^5,category^2,subcategory^2,product_type^2,brand,composition"
  python -m search.evaluate --label hybrid-30-70 --hybrid-weights 0.3,0.7
"""
import argparse
import json
from datetime import date
from pathlib import Path
from statistics import mean

import yaml

from search.metrics import mrr_at_k, ndcg_at_k, recall_at_k
from search.runner import METHODS, run_search

METRICS = {"ndcg": ndcg_at_k, "mrr": mrr_at_k, "recall": recall_at_k}
RESULTS_DIR = Path("search/eval/results")


def load_judgements(path: str) -> list[dict]:
    return yaml.safe_load(Path(path).read_text())["queries"]


def _average(rows: list[dict]) -> dict:
    return {m: round(mean(r[m] for r in rows), 4) for m in METRICS}


def evaluate(search_fn, judgements: list[dict], methods=METHODS, k: int = 10) -> dict:
    results = {}
    for method in methods:
        per_query = {}
        for q in judgements:
            ranked = search_fn(method, q["text"])
            per_query[q["id"]] = {m: fn(ranked, q["grades"], k) for m, fn in METRICS.items()}
        types = sorted({q["type"] for q in judgements})
        results[method] = {
            "overall": _average(list(per_query.values())),
            "by_type": {t: _average([per_query[q["id"]] for q in judgements if q["type"] == t])
                        for t in types},
            "per_query": per_query,
        }
    return results


def to_markdown(results: dict) -> str:
    lines = ["| method | nDCG@10 | MRR@10 | Recall@10 |", "|---|---|---|---|"]
    for method, r in results.items():
        o = r["overall"]
        lines.append(f"| {method} | {o['ndcg']:.3f} | {o['mrr']:.3f} | {o['recall']:.3f} |")
    types = next(iter(results.values()))["by_type"]
    lines += ["", "nDCG@10 by query type:", "",
              "| method | " + " | ".join(types) + " |", "|---" * (len(types) + 1) + "|"]
    for method, r in results.items():
        lines.append(f"| {method} | " + " | ".join(f"{r['by_type'][t]['ndcg']:.3f}" for t in types) + " |")
    return "\n".join(lines)


def main() -> None:
    from search.embed import Embedder
    from search.index import PIPELINE_NAME, ensure_hybrid_pipeline, get_client

    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True)
    p.add_argument("--judgements", default="search/eval/judgements.yaml")
    p.add_argument("--bm25-fields", default=None, help="comma list, e.g. product_name^3,category")
    p.add_argument("--hybrid-weights", default="0.5,0.5", help="BM25,kNN weights")
    p.add_argument("--k", type=int, default=10)
    args = p.parse_args()

    client, embedder = get_client(), Embedder()
    fields = args.bm25_fields.split(",") if args.bm25_fields else None
    weights = tuple(float(w) for w in args.hybrid_weights.split(","))
    pipeline = f"{PIPELINE_NAME}-{args.label}"
    ensure_hybrid_pipeline(client, name=pipeline, weights=weights)

    def search_fn(method, text):
        return run_search(client, embedder, method, text, size=args.k,
                          fields=fields, pipeline=pipeline)

    judgements = load_judgements(args.judgements)
    results = evaluate(search_fn, judgements, k=args.k)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{date.today().isoformat()}-{args.label}.json"
    out.write_text(json.dumps({
        "label": args.label, "date": date.today().isoformat(), "k": args.k,
        "n_queries": len(judgements), "bm25_fields": fields, "hybrid_weights": weights,
        "results": results}, indent=2))
    print(to_markdown(results))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests, expect pass**

Run: `pytest tests/search/test_evaluate.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the real baseline.** Predict first: which method wins overall? Which wins on `descriptive`?

```bash
python -m search.evaluate --label baseline
```

Expected: two Markdown tables and `Saved search/eval/results/<today>-baseline.json`. Paste the real tables back into the session. Compare them with your Task 7 prediction.

- [ ] **Step 6: Commit**

```bash
git add search/evaluate.py tests/search/test_evaluate.py search/eval/results/
git commit -m "feat(search): add evaluation CLI and baseline results"
```

---

### Task 9: Tuning experiments

**Why:** The job ads ask for "statistics to tune relevance". This is that, done honestly: change one thing at a time, measure, keep what helps.

**Files:**
- Create (by running): more files in `search/eval/results/`
- Create: `search/eval/EXPERIMENTS.md`

- [ ] **Step 1: Hybrid weight sweep** (BM25 weight, kNN weight):

```bash
for w in 0.2,0.8 0.3,0.7 0.4,0.6 0.6,0.4 0.7,0.3 0.8,0.2; do
  python -m search.evaluate --label "hybrid-${w/,/-}" --hybrid-weights "$w" | head -6
done
```

Only the `hybrid` row changes between these runs. Note which weight gives the best nDCG@10.

- [ ] **Step 2: BM25 field boosts.** Two variants:

```bash
python -m search.evaluate --label boost-name5 \
  --bm25-fields "product_name^5,product_type^2,category^2,subcategory^2,keywords^2,brand,composition,description"
python -m search.evaluate --label boost-flat \
  --bm25-fields "product_name,product_type,category,subcategory,keywords,brand,composition,description"
```

- [ ] **Step 3: Write `search/eval/EXPERIMENTS.md`.** One table: label, what changed, nDCG@10 / MRR@10 / Recall@10 for the method it affects, and a one-line "kept / dropped". Copy numbers only from the JSON files. Then add a short "What I learned" with 3 bullets in plain words. Warn yourself in writing: with 40 queries, a difference under about 0.02 nDCG is probably noise. Flag any variant whose judged@10 is clearly lower than the baseline's: its score is biased low by unjudged documents.

- [ ] **Step 4: If a variant clearly beat the default,** update `DEFAULT_BM25_FIELDS` in `search/queries.py` and/or `DEFAULT_HYBRID_WEIGHTS` in `search/index.py`, fix `test_bm25_uses_default_boosted_fields` if needed, run `pytest tests/search -q` (expect all pass), and re-run `python -m search.evaluate --label final`.

- [ ] **Step 5: Commit**

```bash
git add search/eval/results/ search/eval/EXPERIMENTS.md search/queries.py search/index.py tests/search/test_queries.py
git commit -m "feat(search): tuning experiments for hybrid weights and BM25 boosts"
```

---

### Task 10: Put indexing into the Airflow DAG

**Why:** "Airflow + OpenSearch" is the exact pair in the job ads. After this, the daily pipeline is extract → dbt → index.

**Files:**
- Modify: `airflow/dags/supply_integration.py`
- Modify: `airflow/docker-compose.override.yml`
- Modify: `airflow/requirements.txt`
- Modify: `run_pipeline.py`

- [ ] **Step 1: Add the task to the DAG.** In `airflow/dags/supply_integration.py`, add this after the `with TaskGroup("transform") as transform_group:` block, still inside `supply_integration()`:

```python
    @task
    def index_search():
        sys.path.insert(0, PROJECT_ROOT)
        from search.embed import Embedder
        from search.index import get_client
        from search.pipeline import run_indexing

        count = run_indexing(os.environ["DUCKDB_PATH"], get_client(), Embedder())
        log.info("Indexed %d products into OpenSearch.", count)

    extract_group >> transform_group >> index_search()
```

Delete the old last line `extract_group >> transform_group`. Update the docstring graph at the top: add `    │\n    index_search  (DuckDB catalog → OpenSearch)` under the transform group.

- [ ] **Step 2: OpenSearch for the Airflow containers.** In `airflow/docker-compose.override.yml`, add `OPENSEARCH_URL: http://opensearch:9200` to the `environment:` of `scheduler`, `webserver` and `triggerer`, and add this service:

```yaml
  opensearch:
    image: opensearchproject/opensearch:2.17.1
    environment:
      - discovery.type=single-node
      - DISABLE_SECURITY_PLUGIN=true
      - DISABLE_INSTALL_DEMO_CONFIG=true
      - OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m
    ports:
      - "9200:9200"
```

(Stop the root-level `docker compose` OpenSearch first, `docker compose stop opensearch`, so port 9200 is free.)

- [ ] **Step 3: Airflow dependencies.** Append to `airflow/requirements.txt`:

```
opensearch-py==2.7.1
pyyaml==6.0.2
sentence-transformers==3.2.1
```

- [ ] **Step 4: Add the step to `run_pipeline.py`** (the non-Airflow runner). Add this function above `if __name__ == "__main__":`

```python
def index():
    logger.info("=== INDEX ===")
    from search.embed import Embedder
    from search.index import get_client
    from search.pipeline import run_indexing

    db_path = os.getenv("DUCKDB_PATH", "data/catalog_data_platform.duckdb")
    logger.info(f"Indexed {run_indexing(db_path, get_client(), Embedder())} products.")
```

and call `index()` after `transform()` in the `__main__` block.

- [ ] **Step 5: Check the DAG file parses**

```bash
python -c "import ast; ast.parse(open('airflow/dags/supply_integration.py').read()); print('ok')"
```

Expected: `ok`.

- [ ] **Step 6: Run the DAG for real.** Needs the Astro CLI (`brew install astro`).

Note before the astro command: data is replayed. Add `RUN_DATE=2026-06-09` and `KES_BASE_URL=offline-replay` to `.env` first, and skip the extract tasks (mark them success) because live feeds need a supplier account code. `dbt test` has 2 known failures (null print prices in the source), so dbt_test will fail and index_search will be upstream_failed unless you run index_search on its own (clear it with 'ignore all deps'). Record honestly what ran.

```bash
cd airflow && astro dev start
# In the UI at http://localhost:8080 (admin / admin), trigger supply_integration.
```

Expected: all tasks green, including `index_search`. Take a screenshot of the graph view for the case study and save it as `docs/img/dag_with_search.png`.

**If you cannot run Astro, stop and say so.** Then the README must say the DAG task is written but was only run through `run_pipeline.py`, not through Airflow, and that `run_pipeline.index()` has not been run.

- [ ] **Step 7: Commit**

```bash
cd ~/code_projects/catalog_data_platform
git add airflow/dags/supply_integration.py airflow/docker-compose.override.yml airflow/requirements.txt run_pipeline.py docs/img/
git commit -m "feat(search): index catalog into OpenSearch as the last DAG task"
```

---

### Task 11: CI, README, and the honest write-up

**Why:** CI proves the tests run on a clean machine. The README is what a recruiter or tech lead actually reads.

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`

- [ ] **Step 1: CI.** In `.github/workflows/ci.yml`, the existing `pip install -r requirements.txt` already picks up `opensearch-py` and `pyyaml`. `pytest tests/` already collects `tests/search/`. The integration test skips because `OPENSEARCH_URL` is not set. Nothing to change unless the run in Step 2 fails.

- [ ] **Step 2: Run the full suite like CI does**

```bash
env -u OPENSEARCH_URL pytest tests/ -q
```

Expected: `28` old tests + the new unit tests pass, `1 skipped` (the integration test). Write down the exact numbers.

- [ ] **Step 3: README section "Search".** Add after the existing pipeline section. It must contain:
  1. One paragraph: what it does (BM25, vector, hybrid over the dbt `catalog` table, indexed by the DAG's last task).
  2. How to run: `docker compose up -d opensearch`, `pip install -r requirements-embed.txt`, `python -m search.evaluate --label baseline`.
  3. The **final** results table, pasted from the JSON output.
  4. The method, in plain words: N queries in three kinds, pooled top-10 from all methods, graded 0–3 by one person.
  5. Limits, in plain words: single grader, small query set, local single-node OpenSearch, not production.

- [ ] **Step 4: Commit and push the branch**

```bash
git add README.md .github/workflows/ci.yml
git commit -m "docs(search): README section with results and method"
git push -u origin feature/opensearch-search
```

Check the GitHub Actions run is green before merging into `main`.

- [ ] **Step 5: Portfolio updates (after merge, separate session).** Refresh `~/code_projects/gavin_skills_catalog_data_platform.md` (new freshness commit, the search section, the real test count, the real results), add the project lines to `~/code_projects/my_skills/skills.md`, and update the case study on gavinjohnreid.com. Every number must be copied from the results JSON.

---

## Interview line this should give you (fill in only after Task 8)

"I added search to my supplier catalogue pipeline: OpenSearch with BM25, vector and hybrid retrieval, indexed as the last Airflow task. I built a 40-query judged set using pooling, graded it myself, and measured nDCG@10. Hybrid scored __ vs __ for BM25, and the gain was mostly on descriptive queries, where BM25 scored __."
