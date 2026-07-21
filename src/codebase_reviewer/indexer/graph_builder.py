from __future__ import annotations

from ..models.chunk import CodeSymbol, SymbolType
from ..models.symbol import GraphEdge, Symbol

_CALL_TYPES = (SymbolType.FUNCTION, SymbolType.METHOD)


class GraphBuilder:
    def __init__(self, parser):
        self._parser = parser
        self._edges: list[GraphEdge] = []

    def build(self, symbols: list[CodeSymbol]) -> tuple[list[Symbol], list[GraphEdge]]:
        fqns = self._derive_fqns(symbols)
        nodes = self._build_nodes(symbols, fqns)
        edges: list[GraphEdge] = []
        edges.extend(self._contains_edges(symbols, fqns))
        edges.extend(self._import_edges(symbols))
        edges.extend(self._call_edges(symbols, fqns))
        edges = self._dedupe(edges)
        self._edges = edges
        return nodes, edges

    def get_neighbors(self, fqn: str) -> dict[str, list[str]]:
        result = {
            "calls": [], "called_by": [], "imports": [],
            "imported_by": [], "contains": [], "contained_in": [],
        }
        for e in self._edges:
            if e.type == "calls":
                if e.source == fqn:
                    result["calls"].append(e.target)
                if e.target == fqn:
                    result["called_by"].append(e.source)
            elif e.type == "imports":
                if e.source == fqn:
                    result["imports"].append(e.target)
                if e.target == fqn:
                    result["imported_by"].append(e.source)
            elif e.type == "contains":
                if e.source == fqn:
                    result["contains"].append(e.target)
                if e.target == fqn:
                    result["contained_in"].append(e.source)
        return result

    def _derive_fqns(self, symbols: list[CodeSymbol]) -> dict[str, str | None]:
        by_id = {s.id: s for s in symbols}
        fqns: dict[str, str | None] = {}
        for s in symbols:
            if s.name is None:
                fqns[s.id] = None
                continue
            parts: list[str] = []
            cur = s
            seen: set[str] = set()
            while cur is not None and cur.id not in seen:
                seen.add(cur.id)
                if cur.name is not None:
                    parts.append(cur.name)
                cur = by_id.get(cur.parent_id) if cur.parent_id is not None else None
            fqns[s.id] = ".".join(reversed(parts))
        return fqns

    def _build_nodes(self, symbols: list[CodeSymbol], fqns: dict[str, str | None]) -> list[Symbol]:
        nodes: list[Symbol] = []
        for s in symbols:
            fqn = fqns[s.id]
            if fqn is None:
                continue
            nodes.append(Symbol(
                fqn=fqn,
                name=s.name,
                type=s.type.value,
                file_path=s.file_path,
                start_line=s.start_line,
                end_line=s.end_line,
                chunk_id=s.id,
                parent_id=s.parent_id,
            ))
        return nodes

    def _contains_edges(self, symbols: list[CodeSymbol], fqns: dict[str, str | None]) -> list[GraphEdge]:
        by_id = {s.id: s for s in symbols}
        edges: list[GraphEdge] = []
        for s in symbols:
            if s.parent_id is None:
                continue
            parent = by_id.get(s.parent_id)
            if parent is None:
                continue
            source = fqns.get(parent.id)
            target = fqns.get(s.id)
            if source is None or target is None:
                continue
            edges.append(GraphEdge(source, target, "contains", parent.file_path, s.file_path))
        return edges

    def _import_edges(self, symbols: list[CodeSymbol]) -> list[GraphEdge]:
        edges: list[GraphEdge] = []
        for s in symbols:
            if s.type != SymbolType.IMPORT:
                continue
            module = self._extract_module(s.content, s.language)
            if module is None:
                continue
            edges.append(GraphEdge(s.file_path, module, "imports", s.file_path, ""))
        return edges

    def _call_edges(self, symbols: list[CodeSymbol], fqns: dict[str, str | None]) -> list[GraphEdge]:
        name_index: dict[str, list[CodeSymbol]] = {}
        for s in symbols:
            if s.name is None:
                continue
            name_index.setdefault(s.name, []).append(s)
        edges: list[GraphEdge] = []
        for s in symbols:
            if s.type not in _CALL_TYPES:
                continue
            caller_fqn = fqns.get(s.id)
            if caller_fqn is None:
                continue
            tree = self._parser.parse(s.content, s.language)
            for call in self._collect_calls(tree.root_node):
                callee = self._callee_name(call)
                if callee is None:
                    continue
                matches = name_index.get(callee, [])
                if len(matches) != 1:
                    continue
                target_fqn = fqns.get(matches[0].id)
                if target_fqn is None:
                    continue
                edges.append(GraphEdge(caller_fqn, target_fqn, "calls", s.file_path, matches[0].file_path))
        return edges

    def _collect_calls(self, root):
        body = self._find_body_block(root)
        scope = body if body is not None else root
        calls: list = []
        self._gather_calls(scope, calls)
        return calls

    def _gather_calls(self, node, out):
        if node.type == "call_expression":
            out.append(node)
        for child in node.children:
            self._gather_calls(child, out)

    def _find_body_block(self, node):
        if node.type == "statement_block":
            return node
        for child in node.children:
            found = self._find_body_block(child)
            if found is not None:
                return found
        return None

    def _callee_name(self, call):
        fn = call.child_by_field_name("function")
        if fn is None:
            return None
        if fn.type == "identifier":
            return fn.text.decode("utf-8")
        if fn.type == "member_expression":
            prop = fn.child_by_field_name("property")
            return prop.text.decode("utf-8") if prop is not None else None
        return None

    def _extract_module(self, content: str, language: str):
        tree = self._parser.parse(content, language)
        module = self._find_import_source(tree.root_node)
        if module is not None:
            return module
        return self._find_require_arg(tree.root_node)

    def _find_import_source(self, node):
        if node.type == "import_statement":
            source = node.child_by_field_name("source")
            if source is not None:
                return self._string_value(source)
        for child in node.children:
            found = self._find_import_source(child)
            if found is not None:
                return found
        return None

    def _find_require_arg(self, node):
        if node.type == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is not None and fn.type == "identifier" and fn.text.decode("utf-8") == "require":
                args = node.child_by_field_name("arguments")
                if args is not None:
                    for child in args.named_children:
                        if child.type == "string":
                            return self._string_value(child)
        for child in node.children:
            found = self._find_require_arg(child)
            if found is not None:
                return found
        return None

    def _string_value(self, string_node):
        for child in string_node.named_children:
            if child.type == "string_fragment":
                return child.text.decode("utf-8")
        return string_node.text.decode("utf-8").strip("'\"`")

    def _dedupe(self, edges: list[GraphEdge]) -> list[GraphEdge]:
        seen: set[tuple[str, str, str]] = set()
        out: list[GraphEdge] = []
        for e in edges:
            key = (e.source, e.target, e.type)
            if key in seen:
                continue
            seen.add(key)
            out.append(e)
        return out
