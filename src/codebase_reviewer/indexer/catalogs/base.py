from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ...models.chunk import SymbolType


@dataclass
class NodeRule:
    match_type: str
    category: SymbolType
    descend_if: Optional[Callable]
    name_extractor: Callable


@dataclass
class Catalog:
    rules: list[NodeRule]

    def match(self, node) -> Optional[NodeRule]:
        for rule in self.rules:
            if rule.match_type != node.type:
                continue
            if rule.descend_if is None or rule.descend_if(node):
                return rule
        return None
