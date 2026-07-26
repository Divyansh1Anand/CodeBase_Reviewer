from __future__ import annotations

from ..models.chunk import CodeSymbol
from .formatter import _format


class ContextBuilder:
    def __init__(self, max_tokens=900_000, reserve_system=2000, reserve_query=500,
                 chars_per_token=3.5):
        self.max_tokens = max_tokens
        self.reserve_system = reserve_system
        self.reserve_query = reserve_query
        self.chars_per_token = chars_per_token

    def _est_tokens(self, text: str) -> float:
        return len(text) / self.chars_per_token

    def _dedupe_containment(self, symbols: list[CodeSymbol]) -> list[CodeSymbol]:
        present_ids = {s.id for s in symbols}
        return [s for s in symbols if not (s.parent_id is not None and s.parent_id in present_ids)]

    def build(self, symbols: list[CodeSymbol], query: str = "") -> str:
        budget = self.max_tokens - self.reserve_system - self.reserve_query - self._est_tokens(query)
        deduped = self._dedupe_containment(symbols)
        parts: list[str] = []
        current = 0.0
        for symbol in deduped:
            formatted = _format(symbol)
            tokens = self._est_tokens(formatted)
            if current + tokens > budget:
                break
            parts.append(formatted)
            current += tokens
        return "\n\n".join(parts)
