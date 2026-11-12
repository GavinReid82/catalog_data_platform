import math

import pytest

from search.metrics import mrr_at_k, ndcg_at_k, recall_at_k

GRADES = {"a": 3, "c": 2}


def test_perfect_order_scores_one():
    assert ndcg_at_k(["a", "c", "x"], GRADES) == pytest.approx(1.0)


def test_ndcg_hand_worked():
    # ranked a, x, c → 3/log2(2) + 0 + 2/log2(4) = 3 + 1 = 4
    # ideal  a, c    → 3/log2(2) + 2/log2(3)     = 3 + 1.26186 = 4.26186
    assert ndcg_at_k(["a", "x", "c"], GRADES) == pytest.approx(4 / (3 + 2 / math.log2(3)))


def test_ndcg_nothing_relevant_found():
    assert ndcg_at_k(["x", "y"], GRADES) == 0.0


def test_ndcg_respects_k():
    assert ndcg_at_k(["x", "a"], GRADES, k=1) == 0.0


def test_mrr_first_hit_at_position_two():
    assert mrr_at_k(["x", "c", "a"], GRADES) == pytest.approx(0.5)


def test_mrr_no_hit():
    assert mrr_at_k(["x", "y"], GRADES) == 0.0


def test_recall_half_found():
    assert recall_at_k(["a", "x"], GRADES) == pytest.approx(0.5)


def test_zero_grade_is_not_relevant():
    assert recall_at_k(["a"], {"a": 0, "b": 1}) == 0.0


def test_empty_grades_score_zero():
    assert ndcg_at_k(["a"], {}) == 0.0
    assert recall_at_k(["a"], {}) == 0.0
