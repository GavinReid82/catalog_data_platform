"""Print the pooled top-10 candidates for a query, ready to grade.

Usage: python -m search.pool "insulated coffee cup"
"""
import sys

from search.embed import Embedder
from search.index import INDEX_NAME, get_client
from search.runner import pool_candidates


def main(text: str) -> None:
    client = get_client()
    ids = pool_candidates(client, Embedder(), text)
    docs = client.mget(index=INDEX_NAME, body={"ids": ids})["docs"]
    print(f"# {text}  ({len(ids)} candidates)")
    for d in docs:
        s = d["_source"]
        print(f'      "{d["_id"]}": 0   # {s["product_name"]} | {s["category"]} / {s["subcategory"]}')


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]))
