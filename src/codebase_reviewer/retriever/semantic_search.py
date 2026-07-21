from __future__ import annotations

from ..models.chunk import CodeSymbol


class SemanticSearch:
    def __init__(self, embedder, chroma_store, top_k=30):
        self.embedder = embedder
        self.chroma_store = chroma_store
        self.top_k = top_k

    def search(self, query: str) -> list[CodeSymbol]:
        vector = self.embedder.embed_query(query)
        return self.chroma_store.query(vector, self.top_k)
