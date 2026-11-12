"""Run every judged query through every method and score it.

Usage:
  python -m search.evaluate --label baseline
  python -m search.evaluate --label boosts-name5 --bm25-fields "product_name^5,category^2,subcategory^2,product_type^2,brand,composition"
  python -m search.evaluate --label hybrid-30-70 --hybrid-weights 0.3,0.7
"""
import argparse
import json
from datetime import date
from pathlib import Path
from statistics import mean

import yaml

from search.metrics import mrr_at_k, ndcg_at_k, recall_at_k
from search.runner import METHODS, run_search

METRICS = {"ndcg": ndcg_at_k, "mrr": mrr_at_k, "recall": recall_at_k}
RESULTS_DIR = Path("search/eval/results")


def load_judgements(path: str) -> list[dict]:
    return yaml.safe_load(Path(path).read_text())["queries"]


def _average(rows: list[dict]) -> dict:
    return {m: round(mean(r[m] for r in rows), 4) for m in METRICS}


def evaluate(search_fn, judgements: list[dict], methods=METHODS, k: int = 10) -> dict:
    results = {}
    for method in methods:
        per_query = {}
        for q in judgements:
            ranked = search_fn(method, q["text"])
            per_query[q["id"]] = {m: fn(ranked, q["grades"], k) for m, fn in METRICS.items()}
        types = sorted({q["type"] for q in judgements})
        results[method] = {
            "overall": _average(list(per_query.values())),
            "by_type": {t: _average([per_query[q["id"]] for q in judgements if q["type"] == t])
                        for t in types},
            "per_query": per_query,
        }
    return results


def to_markdown(results: dict) -> str:
    lines = ["| method | nDCG@10 | MRR@10 | Recall@10 |", "|---|---|---|---|"]
    for method, r in results.items():
        o = r["overall"]
        lines.append(f"| {method} | {o['ndcg']:.3f} | {o['mrr']:.3f} | {o['recall']:.3f} |")
    types = next(iter(results.values()))["by_type"]
    lines += ["", "nDCG@10 by query type:", "",
              "| method | " + " | ".join(types) + " |", "|---" * (len(types) + 1) + "|"]
    for method, r in results.items():
        lines.append(f"| {method} | " + " | ".join(f"{r['by_type'][t]['ndcg']:.3f}" for t in types) + " |")
    return "\n".join(lines)


def main() -> None:
    from search.embed import Embedder
    from search.index import PIPELINE_NAME, ensure_hybrid_pipeline, get_client

    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True)
    p.add_argument("--judgements", default="search/eval/judgements.yaml")
    p.add_argument("--bm25-fields", default=None, help="comma list, e.g. product_name^3,category")
    p.add_argument("--hybrid-weights", default="0.5,0.5", help="BM25,kNN weights")
    p.add_argument("--k", type=int, default=10)
    args = p.parse_args()

    client, embedder = get_client(), Embedder()
    fields = args.bm25_fields.split(",") if args.bm25_fields else None
    weights = tuple(float(w) for w in args.hybrid_weights.split(","))
    pipeline = f"{PIPELINE_NAME}-{args.label}"
    ensure_hybrid_pipeline(client, name=pipeline, weights=weights)

    def search_fn(method, text):
        return run_search(client, embedder, method, text, size=args.k,
                          fields=fields, pipeline=pipeline)

    judgements = load_judgements(args.judgements)
    results = evaluate(search_fn, judgements, k=args.k)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{date.today().isoformat()}-{args.label}.json"
    out.write_text(json.dumps({
        "label": args.label, "date": date.today().isoformat(), "k": args.k,
        "n_queries": len(judgements), "bm25_fields": fields, "hybrid_weights": weights,
        "results": results}, indent=2))
    print(to_markdown(results))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
