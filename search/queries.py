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
