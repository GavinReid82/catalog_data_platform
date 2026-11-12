# search/pool.py
"""Print the pooled top-10 candidates for a query, ready to grade.

Usage: python -m search.pool "insulated coffee cup"
"""
import random
import sys

from search.embed import Embedder
from search.index import INDEX_NAME, get_client
from search.runner import pool_candidates

DESCRIPTION_CHARS = 120


def format_line(doc_id: str, source: dict) -> str:
    where = source.get("category") or ""
    if source.get("subcategory"):
        where += f' / {source["subcategory"]}'
    desc = " ".join((source.get("description") or "").split())[:DESCRIPTION_CHARS]
    line = f'      "{doc_id}": 0   # {source.get("product_name")} | {where}'
    return f"{line} | {desc}" if desc else line


def render(text: str, ids: list[str], docs: list[dict]) -> list[str]:
    lines = [f"# {text}  ({len(ids)} candidates)"]
    lines += [format_line(d["_id"], d["_source"]) for d in docs if d.get("found", True)]
    return lines


def main(text: str) -> None:
    client = get_client()
    ids = pool_candidates(client, Embedder(), text)
    random.Random(text).shuffle(ids)  # reproducible; hides which method found what
    docs = client.mget(index=INDEX_NAME, body={"ids": ids})["docs"] if ids else []
    print("\n".join(render(text, ids, docs)))


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]))
