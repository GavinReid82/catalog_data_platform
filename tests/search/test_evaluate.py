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


# --- final review fixes ---
import argparse

from search.evaluate import (judged_at_k, label_type, missing_ids,
                             resolve_weights)
from search.index import DEFAULT_HYBRID_WEIGHTS


def test_default_hybrid_weights_constant():
    assert DEFAULT_HYBRID_WEIGHTS == (0.5, 0.5)
    import inspect
    from search.index import ensure_hybrid_pipeline
    assert inspect.signature(ensure_hybrid_pipeline).parameters["weights"].default is DEFAULT_HYBRID_WEIGHTS


def test_resolve_weights():
    assert resolve_weights(None) == DEFAULT_HYBRID_WEIGHTS
    assert resolve_weights("0.3,0.7") == (0.3, 0.7)


class FakeClient:
    def __init__(self, present):
        self.present = set(present)

    def mget(self, index, body):
        return {"docs": [{"_id": i, "found": i in self.present} for i in body["ids"]]}


def test_missing_ids_lists_absent_graded_ids():
    j = [{"id": "q1", "grades": {"a": 3, "b": 0}}, {"id": "q2", "grades": {"c": 2, "a": 1}}]
    assert missing_ids(FakeClient({"a", "c"}), "products", j) == ["b"]
    assert missing_ids(FakeClient({"a", "b", "c"}), "products", j) == []


def test_judged_at_k():
    assert judged_at_k(["a", "x", "b", "y"], {"a": 3, "b": 0}, 4) == 0.5
    assert judged_at_k(["a", "x", "b", "y"], {"a": 3, "b": 0}, 2) == 0.5
    assert judged_at_k(["a"], {"a": 3}, 10) == 1.0
    assert judged_at_k([], {"a": 3}, 10) == 0.0


def test_judged_in_results_but_not_in_relevance_metrics():
    from search.evaluate import METRICS
    assert "judged" not in METRICS
    r = evaluate(fake_search, JUDGEMENTS, methods=("vector",))
    assert r["vector"]["per_query"]["q1"]["judged"] == 0.5
    assert r["vector"]["per_query"]["q2"]["judged"] == 1.0
    assert r["vector"]["overall"]["judged"] == 0.75
    assert r["vector"]["by_type"]["keyword"]["judged"] == 0.5


def test_markdown_has_judged_column():
    md = to_markdown(evaluate(fake_search, JUDGEMENTS, methods=("vector",)), k=10)
    assert "| judged@10 |" in md
    assert "| vector | 0.816 | 0.750 | 1.000 | 0.750 |" in md


def _write(tmp_path, body):
    f = tmp_path / "j.yaml"
    f.write_text(body)
    return str(f)


def test_load_judgements_rejects_bad_grades(tmp_path):
    for bad in ("5", "-1", "1.5", "high", "true"):
        f = _write(tmp_path, f"queries:\n  - {{id: q1, type: k, text: a, grades: {{x: {bad}, y: 3}}}}\n")
        with pytest.raises(ValueError, match="q1"):
            load_judgements(f)


def test_load_judgements_rejects_query_without_relevant(tmp_path):
    f = _write(tmp_path,
               "queries:\n  - {id: q1, type: k, text: a, grades: {x: 0}}\n"
               "  - {id: q2, type: k, text: b, grades: {}}\n"
               "  - {id: q3, type: k, text: c, grades: {x: 1}}\n")
    with pytest.raises(ValueError, match=r"q1.*q2|q2.*q1") as e:
        load_judgements(f)
    assert "q3" not in str(e.value)


def test_label_type():
    assert label_type("boost-name5_v1.2") == "boost-name5_v1.2"
    for bad in ("", "a b", "../x", "a/b", "x;y"):
        with pytest.raises(argparse.ArgumentTypeError):
            label_type(bad)
