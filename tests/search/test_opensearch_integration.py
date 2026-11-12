import os

import duckdb
import pytest

pytestmark = pytest.mark.skipif(not os.getenv("OPENSEARCH_URL"),
                                reason="needs a running OpenSearch (set OPENSEARCH_URL)")

from search.index import PIPELINE_NAME, get_client  # noqa: E402
from search.pipeline import run_indexing  # noqa: E402
from search.queries import bm25_query, hybrid_query  # noqa: E402

TEST_INDEX = "products_test"
WORDS = ["bottle", "bag", "pen", "mug"]


class FakeEmbedder:
    dim = 4

    def embed(self, texts):
        return [[1.0 if w in t.lower() else 0.01 for w in WORDS] for t in texts]


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "t.duckdb")
    con = duckdb.connect(path)
    con.execute("""
        create table catalog as select * from (values
          ('vta', 'A1', 'Steel water bottle', 'Drinkware'),
          ('vta', 'A2', 'Cotton tote bag', 'Bags'),
          ('vta', 'A3', 'Ballpoint pen', 'Writing')
        ) t(supplier, product_ref, product_name, category)
    """)
    con.close()
    return path


def test_index_then_search(db):
    client = get_client()
    assert run_indexing(db, client, FakeEmbedder(), index=TEST_INDEX) == 3

    hits = client.search(index=TEST_INDEX, body=bm25_query("bottle"))["hits"]["hits"]
    assert hits[0]["_id"] == "vta:A1"

    body = hybrid_query("bag", FakeEmbedder().embed(["bag"])[0])
    resp = client.transport.perform_request(
        "POST", f"/{TEST_INDEX}/_search", params={"search_pipeline": PIPELINE_NAME}, body=body)
    assert resp["hits"]["hits"][0]["_id"] == "vta:A2"

    client.indices.delete(index=TEST_INDEX)
