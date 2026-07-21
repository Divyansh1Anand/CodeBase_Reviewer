from __future__ import annotations

from ..models.chunk import CodeSymbol, SymbolType

_BLOCK_MAP = {
    "if_statement": SymbolType.IF_BLOCK,
    "else_clause": SymbolType.IF_BLOCK,
    "for_statement": SymbolType.LOOP_BLOCK,
    "for_in_statement": SymbolType.LOOP_BLOCK,
    "while_statement": SymbolType.LOOP_BLOCK,
    "do_statement": SymbolType.LOOP_BLOCK,
    "try_statement": SymbolType.TRY_BLOCK,
}

_SPLIT_TYPES = (SymbolType.FUNCTION, SymbolType.METHOD)
_MERGE_TYPES = (SymbolType.CONSTANT, SymbolType.VARIABLE)


class SizeNormalizer:
    def __init__(self, parser, max_tokens=2000, min_tokens=50):
        self._parser = parser
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens

    def normalize(self, symbols: list[CodeSymbol]) -> list[CodeSymbol]:
        split_result: list[CodeSymbol] = []
        for symbol in symbols:
            split_result.append(symbol)
            if symbol.type in _SPLIT_TYPES and self._est(symbol.content) > self.max_tokens:
                split_result.extend(self._split(symbol))
        return self._merge(split_result)

    def _est(self, content: str) -> int:
        return len(content) // 4

    def _find_body_block(self, node):
        if node.type == "statement_block":
            return node
        for child in node.children:
            found = self._find_body_block(child)
            if found is not None:
                return found
        return None

    def _split(self, symbol: CodeSymbol) -> list[CodeSymbol]:
        tree = self._parser.parse(symbol.content, symbol.language)
        body = self._find_body_block(tree.root_node)
        if body is None:
            return []
        blocks: list[CodeSymbol] = []
        for node in body.named_children:
            mapped = _BLOCK_MAP.get(node.type)
            if mapped is None:
                continue
            start_line = symbol.start_line + node.start_point[0]
            end_line = symbol.start_line + node.end_point[0]
            content = node.text.decode("utf-8")
            blocks.append(CodeSymbol(
                id=CodeSymbol.make_id(symbol.file_path, start_line, end_line, mapped),
                parent_id=symbol.id,
                name=None,
                type=mapped,
                fqn=None,
                file_path=symbol.file_path,
                start_line=start_line,
                end_line=end_line,
                content=content,
                language=symbol.language,
            ))
        return blocks

    def _merge(self, symbols: list[CodeSymbol]) -> list[CodeSymbol]:
        candidates = [s for s in symbols if s.parent_id is None and s.type in _MERGE_TYPES]
        ordered = sorted(candidates, key=lambda s: (s.file_path, s.start_line))
        groups = []
        current = []
        for s in ordered:
            if self._est(s.content) >= self.min_tokens:
                if len(current) >= 2:
                    groups.append(current)
                current = []
                continue
            if current and current[-1].file_path != s.file_path:
                if len(current) >= 2:
                    groups.append(current)
                current = [s]
            else:
                current.append(s)
        if len(current) >= 2:
            groups.append(current)

        first_map = {}
        skip = set()
        for group in groups:
            first_map[id(group[0])] = self._merge_group(group)
            for member in group[1:]:
                skip.add(id(member))

        out: list[CodeSymbol] = []
        for s in symbols:
            if id(s) in skip:
                continue
            if id(s) in first_map:
                out.append(first_map[id(s)])
            else:
                out.append(s)
        return out

    def _merge_group(self, group: list[CodeSymbol]) -> CodeSymbol:
        first = group[0]
        last = group[-1]
        return CodeSymbol(
            id=CodeSymbol.make_id(first.file_path, first.start_line, last.end_line, SymbolType.CONSTANT),
            parent_id=None,
            name=None,
            type=SymbolType.CONSTANT,
            fqn=None,
            file_path=first.file_path,
            start_line=first.start_line,
            end_line=last.end_line,
            content="\n".join(m.content for m in group),
            language=first.language,
        )
