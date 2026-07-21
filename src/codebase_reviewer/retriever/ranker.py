from __future__ import annotations

from ..models.chunk import CodeSymbol


def reciprocal_rank_fusion(ranked_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    order: list[str] = []
    for ranked in ranked_lists:
        for index, item in enumerate(ranked):
            if item not in scores:
                scores[item] = 0.0
                order.append(item)
            scores[item] += 1.0 / (k + index + 1)
    return sorted(((item, scores[item]) for item in order), key=lambda pair: -pair[1])


class Ranker:
    def __init__(self, rrf_k=60):
        self.rrf_k = rrf_k

    def fuse_and_rank(self, semantic_results: list[CodeSymbol], keyword_results: list[CodeSymbol]) -> list[CodeSymbol]:
        semantic_ids = [s.id for s in semantic_results]
        keyword_ids = [s.id for s in keyword_results]
        fused = reciprocal_rank_fusion([semantic_ids, keyword_ids], self.rrf_k)
        by_id: dict[str, CodeSymbol] = {}
        for symbol in semantic_results:
            by_id.setdefault(symbol.id, symbol)
        for symbol in keyword_results:
            by_id.setdefault(symbol.id, symbol)
        out: list[CodeSymbol] = []
        for item_id, _score in fused:
            symbol = by_id.get(item_id)
            if symbol is not None:
                out.append(symbol)
        return out
