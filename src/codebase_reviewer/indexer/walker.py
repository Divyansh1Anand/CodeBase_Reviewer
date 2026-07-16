from __future__ import annotations

from collections import Counter

from ..models.chunk import CodeSymbol
from .catalogs import REGISTRY


class Walker:
    def chunk(self, tree, source: str, file_path: str, language: str) -> list[CodeSymbol]:
        source_bytes = bytes(source, "utf-8")
        symbols: list[CodeSymbol] = []
        self.unmatched_types: Counter = Counter()

        catalog = self._lookup_catalog(language)

        def walk(node, parent_id: str | None) -> None:
            rule = self._match(catalog, node)

            if rule is not None and rule.descend_if is not None and not rule.descend_if(node):
                rule = None

            if rule is not None:
                symbol = self._build_symbol(rule, node, source_bytes, file_path, language, parent_id)
                symbols.append(symbol)
                child_parent_id = symbol.id
            else:
                if node.is_named:
                    self.unmatched_types[node.type] += 1
                child_parent_id = parent_id

            for child in node.children:
                walk(child, child_parent_id)

        walk(tree.root_node, None)
        return symbols

    def _lookup_catalog(self, language: str):
        return REGISTRY.get(language)

    def _match(self, catalog, node):
        if catalog is None:
            return None
        return catalog.match(node)

    def _build_symbol(self, rule, node, source_bytes: bytes, file_path: str,
                      language: str, parent_id: str | None) -> CodeSymbol:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        content = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
        name = rule.name_extractor(node)
        return CodeSymbol(
            id=CodeSymbol.make_id(file_path, start_line, end_line, rule.category),
            parent_id=parent_id,
            name=name,
            type=rule.category,
            fqn=None,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            content=content,
            language=language,
        )
