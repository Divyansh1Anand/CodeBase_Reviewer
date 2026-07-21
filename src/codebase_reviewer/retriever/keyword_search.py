from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from ..models.chunk import CodeSymbol

_TOKEN = re.compile(r"\w+")


class KeywordSearch:
    def __init__(self, top_k=30):
        self.top_k = top_k

    def _tokenize(self, text: str) -> list[str]:
        return [token.lower() for token in _TOKEN.findall(text)]

    def search(self, query: str, corpus: list[CodeSymbol]) -> list[CodeSymbol]:
        if not corpus:
            return []
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        tokenized_corpus = [self._tokenize(symbol.content) for symbol in corpus]
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query_tokens)
        ranked = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)
        return [corpus[i] for i in ranked[:self.top_k]]
