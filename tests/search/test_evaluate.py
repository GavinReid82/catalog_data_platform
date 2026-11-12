import pytest

from search.evaluate import evaluate, load_judgements, to_markdown

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


def test_markdown_labels_follow_k():
    md = to_markdown(evaluate(fake_search, JUDGEMENTS, methods=("bm25",), k=5), k=5)
    assert "nDCG@5" in md and "MRR@5" in md and "Recall@5" in md
    assert "@10" not in md


def test_markdown_by_type_table_has_ndcg():
    md = to_markdown(evaluate(fake_search, JUDGEMENTS, methods=("bm25", "vector")))
    assert "| method | descriptive | keyword |" in md
    assert "| bm25 | 0.000 | 1.000 |" in md
    assert "| vector | 1.000 | 0.631 |" in md


def test_load_judgements_rejects_empty(tmp_path):
    f = tmp_path / "j.yaml"
    f.write_text("queries: []\n")
    with pytest.raises(ValueError, match="no queries"):
        load_judgements(str(f))
    f.write_text("")
    with pytest.raises(ValueError, match="no queries"):
        load_judgements(str(f))


def test_load_judgements_rejects_duplicate_ids(tmp_path):
    f = tmp_path / "j.yaml"
    f.write_text(
        "queries:\n"
        "  - {id: q1, type: keyword, text: a, grades: {x: 3}}\n"
        "  - {id: q1, type: keyword, text: b, grades: {x: 3}}\n")
    with pytest.raises(ValueError, match="q1"):
        load_judgements(str(f))


def test_load_judgements_ok(tmp_path):
    f = tmp_path / "j.yaml"
    f.write_text("queries:\n  - {id: q1, type: keyword, text: a, grades: {x: 3}}\n")
    assert load_judgements(str(f))[0]["id"] == "q1"


def test_evaluate_honours_k():
    j = [{"id": "q1", "type": "keyword", "text": "t", "grades": {"a": 3}}]
    fn = lambda method, text: ["x", "a"]
    assert evaluate(fn, j, methods=("bm25",), k=10)["bm25"]["overall"]["mrr"] == 0.5
    assert evaluate(fn, j, methods=("bm25",), k=1)["bm25"]["overall"]["mrr"] == 0.0
