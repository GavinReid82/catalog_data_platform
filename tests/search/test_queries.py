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
