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
