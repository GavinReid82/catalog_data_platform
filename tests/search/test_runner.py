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
