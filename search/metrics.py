"""Ranking metrics. `ranked` is the result list, best first. `grades` maps doc id → 0–3."""
import math


def _dcg(gains: list[int]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranked: list[str], grades: dict[str, int], k: int = 10) -> float:
    ideal = _dcg(sorted(grades.values(), reverse=True)[:k])
    if ideal == 0:
        return 0.0
    return _dcg([grades.get(d, 0) for d in ranked[:k]]) / ideal


def mrr_at_k(ranked: list[str], grades: dict[str, int], k: int = 10) -> float:
    for position, d in enumerate(ranked[:k], start=1):
        if grades.get(d, 0) > 0:
            return 1 / position
    return 0.0


def recall_at_k(ranked: list[str], grades: dict[str, int], k: int = 10) -> float:
    relevant = {d for d, g in grades.items() if g > 0}
    if not relevant:
        return 0.0
    return len(relevant & set(ranked[:k])) / len(relevant)
