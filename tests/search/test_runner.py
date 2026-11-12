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
        self.bodies = []
        self.transport = FakeTransport(ids_by_kind["hybrid"])

    def search(self, index, body):
        self.bodies.append(body)
        kind = "bm25" if "multi_match" in body["query"] else "vector"
        return {"hits": {"hits": [{"_id": i} for i in self.ids_by_kind[kind]]}}


IDS = {"bm25": ["a", "b"], "vector": ["c", "a"], "hybrid": ["a", "c"]}


@pytest.mark.parametrize("method", ["bm25", "vector", "hybrid"])
def test_run_search_returns_ids_for_each_method(method):
    assert run_search(FakeClient(IDS), FakeEmbedder(), method, "x") == IDS[method]


def test_hybrid_goes_through_the_search_pipeline():
    client = FakeClient(IDS)
    run_search(client, FakeEmbedder(), "hybrid", "x", pipeline="p1")
    method, url, params, body = client.transport.calls[0]
    assert (method, params) == ("POST", {"search_pipeline": "p1"})
    assert url.endswith("/_search")
    subs = body["query"]["hybrid"]["queries"]
    assert "multi_match" in subs[0] and subs[1]["knn"]["embedding"]["vector"] == [0.5, 0.5]
    assert body["size"] == 10


def test_unknown_method_raises():
    with pytest.raises(ValueError):
        run_search(FakeClient(IDS), FakeEmbedder(), "magic", "x")


def test_pool_is_unique_in_first_seen_order():
    assert pool_candidates(FakeClient(IDS), FakeEmbedder(), "x") == ["a", "b", "c"]


def test_size_reaches_the_query_body():
    client = FakeClient(IDS)
    run_search(client, FakeEmbedder(), "bm25", "x", size=7)
    run_search(client, FakeEmbedder(), "vector", "x", size=7)
    run_search(client, FakeEmbedder(), "hybrid", "x", size=7)
    assert [b["size"] for b in client.bodies] == [7, 7]
    assert client.transport.calls[0][3]["size"] == 7


def test_bm25_fields_reach_the_multi_match():
    client = FakeClient(IDS)
    run_search(client, FakeEmbedder(), "bm25", "x", fields=["product_name"])
    assert client.bodies[0]["query"]["multi_match"]["fields"] == ["product_name"]


def test_vector_body_uses_the_embedder_vector():
    client = FakeClient(IDS)
    run_search(client, FakeEmbedder(), "vector", "x")
    assert client.bodies[0]["query"]["knn"]["embedding"]["vector"] == [0.5, 0.5]


def test_pool_depth_reaches_every_method():
    client = FakeClient(IDS)
    pool_candidates(client, FakeEmbedder(), "x", depth=4)
    assert [b["size"] for b in client.bodies] == [4, 4]
    assert client.transport.calls[0][3]["size"] == 4
