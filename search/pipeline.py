"""DuckDB catalog → embeddings → OpenSearch."""
import logging

from search.documents import load_catalog
from search.index import INDEX_NAME, bulk_index, ensure_hybrid_pipeline, recreate_index

log = logging.getLogger(__name__)


def run_indexing(db_path: str, client, embedder, index: str = INDEX_NAME) -> int:
    docs = load_catalog(db_path)
    log.info("Loaded %d products from %s", len(docs), db_path)
    vectors = embedder.embed([d["search_text"] for d in docs])
    recreate_index(client, index, embedder.dim)
    count = bulk_index(client, index, docs, vectors)
    ensure_hybrid_pipeline(client)
    log.info("Indexed %d documents into %s", count, index)
    return count
