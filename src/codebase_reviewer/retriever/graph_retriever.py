from __future__ import annotations

from typing import Callable, Optional

from ..models.chunk import CodeSymbol

_DIRECTIONS = ("calls", "called_by", "imports", "imported_by", "contains", "contained_in")


class GraphRetriever:
    def __init__(self, graph_store, resolver: Callable[[str], Optional[CodeSymbol]], depth=1):
        self.graph_store = graph_store
        self.resolver = resolver
        self.depth = depth

    def expand(self, symbols: list[CodeSymbol]) -> list[CodeSymbol]:
        result = list(symbols)
        seen = {s.id for s in symbols}
        frontier = list(symbols)
        for _ in range(self.depth):
            next_frontier: list[CodeSymbol] = []
            for symbol in frontier:
                if symbol.fqn is None:
                    continue
                neighbors = self.graph_store.neighbors(symbol.fqn)
                for direction in _DIRECTIONS:
                    for fqn in neighbors.get(direction, []):
                        resolved = self.resolver(fqn)
                        if resolved is None:
                            continue
                        if resolved.id in seen:
                            continue
                        seen.add(resolved.id)
                        result.append(resolved)
                        next_frontier.append(resolved)
            frontier = next_frontier
        return result
