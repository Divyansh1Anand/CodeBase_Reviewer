from __future__ import annotations

from ..models.chunk import CodeSymbol


class Retriever:
    def __init__(self, semantic_search, keyword_search, ranker, graph_retriever):
        self.semantic_search = semantic_search
        self.keyword_search = keyword_search
        self.ranker = ranker
        self.graph_retriever = graph_retriever

    def retrieve(self, query: str, corpus: list[CodeSymbol], top_k=20) -> list[CodeSymbol]:
        semantic_results = self.semantic_search.search(query)
        keyword_results = self.keyword_search.search(query, corpus)
        fused = self.ranker.fuse_and_rank(semantic_results, keyword_results)
        top = fused[:top_k]
        expanded = self.graph_retriever.expand(top)
        seen: set[str] = set()
        out: list[CodeSymbol] = []
        for symbol in expanded:
            if symbol.id in seen:
                continue
            seen.add(symbol.id)
            out.append(symbol)
        return out
