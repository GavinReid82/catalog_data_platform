from search.pool import format_line, render


def test_format_line_truncates_and_collapses_whitespace():
    src = {"product_name": "Mug", "category": "Drinkware", "subcategory": "Mugs",
           "description": "a  b\n" + "x" * 300}
    line = format_line("kes:1", src)
    assert line.startswith('      "kes:1": 0   # Mug | Drinkware / Mugs | a b x')
    assert "\n" not in line
    assert len(line.split(" | ")[-1]) == 120


def test_format_line_omits_empty_subcategory_and_description():
    src = {"product_name": "Mikix", "category": "Kids", "subcategory": "", "description": None}
    assert format_line("vta:1", src) == '      "vta:1": 0   # Mikix | Kids'


def test_render_empty_pool_prints_header_only():
    assert render("q", [], []) == ["# q  (0 candidates)"]


def test_render_skips_missing_docs():
    docs = [{"_id": "a", "found": False},
            {"_id": "b", "found": True, "_source": {"product_name": "P", "category": "C"}}]
    out = render("q", ["a", "b"], docs)
    assert out[0] == "# q  (2 candidates)"
    assert len(out) == 2 and '"b"' in out[1]


def test_main_without_query_prints_usage_and_exits_2(capsys):
    import pytest
    from search.pool import cli
    with pytest.raises(SystemExit) as e:
        cli([])
    assert e.value.code == 2
    assert "usage" in capsys.readouterr().err.lower()
