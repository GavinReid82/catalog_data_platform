"""Run every judged query through every method and score it.

Usage:
  python -m search.evaluate --label baseline
  python -m search.evaluate --label boosts-name5 --bm25-fields "product_name^5,product_type^2,category^2,subcategory^2,keywords^2,brand,composition,description"
  python -m search.evaluate --label hybrid-30-70 --hybrid-weights 0.3,0.7
"""
import argparse
import json
import re
from datetime import date
from pathlib import Path
from statistics import mean

import yaml

from search.index import DEFAULT_HYBRID_WEIGHTS
from search.metrics import mrr_at_k, ndcg_at_k, recall_at_k
from search.runner import METHODS, run_search

METRICS = {"ndcg": ndcg_at_k, "mrr": mrr_at_k, "recall": recall_at_k}
RESULTS_DIR = Path("search/eval/results")
LABEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def judged_at_k(ranked: list[str], grades: dict[str, int], k: int = 10) -> float:
    """Share of the top-k results that appear in the query's grades (any grade, 0 included).

    Not a relevance score: it shows how much of the ranking was ever judged. Unjudged
    documents count as wrong in the metrics above, so a low value biases them down.
    """
    top = ranked[:k]
    if not top:
        return 0.0
    return sum(d in grades for d in top) / len(top)


def label_type(value: str) -> str:
    if not LABEL_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"label {value!r} must match [A-Za-z0-9._-]+ (it becomes part of a file name)")
    return value


def resolve_weights(arg: str | None) -> tuple[float, float]:
    if arg is None:
        return DEFAULT_HYBRID_WEIGHTS
    return tuple(float(w) for w in arg.split(","))


def missing_ids(client, index: str, judgements: list[dict]) -> list[str]:
    """Graded ids that are not in the index (typos, or documents lost on a re-index)."""
    ids = sorted({d for q in judgements for d in q["grades"]})
    if not ids:
        return []
    docs = client.mget(index=index, body={"ids": ids})["docs"]
    return [d["_id"] for d in docs if not d.get("found")]


def load_judgements(path: str) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text()) or {}
    queries = data.get("queries") if isinstance(data, dict) else None
    if not queries:
        raise ValueError(f"{path} has no queries")
    for q in queries:
        bad = {d: g for d, g in q["grades"].items()
               if isinstance(g, bool) or not isinstance(g, int) or not 0 <= g <= 3}
        if bad:
            raise ValueError(f"query {q['id']} has grades that are not ints 0-3: {bad}")
    no_relevant = [str(q["id"]) for q in queries if not any(g > 0 for g in q["grades"].values())]
    if no_relevant:
        raise ValueError(f"{path} has queries with no grade above 0: {', '.join(no_relevant)}")
    ids = [q["id"] for q in queries]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"{path} has duplicate query ids: {', '.join(map(str, dupes))}")
    return queries


def _average(rows: list[dict]) -> dict:
    return {m: round(mean(r[m] for r in rows), 4) for m in (*METRICS, "judged")}


def evaluate(search_fn, judgements: list[dict], methods=METHODS, k: int = 10) -> dict:
    results = {}
    for method in methods:
        per_query = {}
        for q in judgements:
            ranked = search_fn(method, q["text"])
            per_query[q["id"]] = {m: fn(ranked, q["grades"], k) for m, fn in METRICS.items()}
            per_query[q["id"]]["judged"] = judged_at_k(ranked, q["grades"], k)
        types = sorted({q["type"] for q in judgements})
        results[method] = {
            "overall": _average(list(per_query.values())),
            "by_type": {t: _average([per_query[q["id"]] for q in judgements if q["type"] == t])
                        for t in types},
            "per_query": per_query,
        }
    return results


def to_markdown(results: dict, k: int = 10) -> str:
    lines = [f"| method | nDCG@{k} | MRR@{k} | Recall@{k} | judged@{k} |", "|---|---|---|---|---|"]
    for method, r in results.items():
        o = r["overall"]
        lines.append(f"| {method} | {o['ndcg']:.3f} | {o['mrr']:.3f} | {o['recall']:.3f} | {o['judged']:.3f} |")
    types = next(iter(results.values()))["by_type"]
    lines += ["", f"nDCG@{k} by query type:", "",
              "| method | " + " | ".join(types) + " |", "|---" * (len(types) + 1) + "|"]
    for method, r in results.items():
        lines.append(f"| {method} | " + " | ".join(f"{r['by_type'][t]['ndcg']:.3f}" for t in types) + " |")
    return "\n".join(lines)


def main() -> None:
    from search.embed import Embedder
    from search.embed import MODEL_NAME
    from search.index import INDEX_NAME, PIPELINE_NAME, ensure_hybrid_pipeline, get_client
    from search.queries import DEFAULT_BM25_FIELDS

    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True, type=label_type)
    p.add_argument("--judgements", default="search/eval/judgements.yaml")
    p.add_argument("--bm25-fields", default=None, help="comma list, e.g. product_name^3,category")
    p.add_argument("--hybrid-weights", default=None,
                   help="BM25,kNN weights (default: DEFAULT_HYBRID_WEIGHTS in search/index.py)")
    p.add_argument("--k", type=int, default=10)
    args = p.parse_args()

    judgements = load_judgements(args.judgements)
    client, embedder = get_client(), Embedder()
    fields = args.bm25_fields.split(",") if args.bm25_fields else None
    weights = resolve_weights(args.hybrid_weights)
    absent = missing_ids(client, INDEX_NAME, judgements)
    if absent:
        raise SystemExit(f"{len(absent)} judged ids are not in index {INDEX_NAME!r}: {', '.join(absent)}")
    pipeline = f"{PIPELINE_NAME}-{args.label}"
    ensure_hybrid_pipeline(client, name=pipeline, weights=weights)

    def search_fn(method, text):
        return run_search(client, embedder, method, text, size=args.k,
                          fields=fields, pipeline=pipeline)

    results = evaluate(search_fn, judgements, k=args.k)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    out = RESULTS_DIR / f"{today}-{args.label}.json"
    out.write_text(json.dumps({
        "label": args.label, "date": today, "k": args.k,
        "n_queries": len(judgements), "judgements": args.judgements,
        "index": INDEX_NAME, "index_doc_count": client.count(index=INDEX_NAME)["count"],
        "pipeline": pipeline, "embedding_model": MODEL_NAME,
        "bm25_fields": fields or DEFAULT_BM25_FIELDS, "hybrid_weights": weights,
        "results": results}, indent=2))
    print(to_markdown(results, args.k))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
