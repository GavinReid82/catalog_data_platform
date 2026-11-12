from search.index import ANALYZER, index_body


def test_index_body_has_vector_field_with_right_dimension():
    body = index_body(dim=384)
    emb = body["mappings"]["properties"]["embedding"]
    assert emb["type"] == "knn_vector"
    assert emb["dimension"] == 384
    assert emb["method"]["space_type"] == "cosinesimil"
    assert body["settings"]["index"]["knn"] is True


def test_text_fields_use_the_language_analyzer():
    props = index_body(dim=4)["mappings"]["properties"]
    assert props["product_name"] == {"type": "text", "analyzer": ANALYZER}
    assert props["supplier"] == {"type": "keyword"}
