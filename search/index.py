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
