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
