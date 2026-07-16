from __future__ import annotations

from ...models.chunk import SymbolType
from .base import Catalog, NodeRule
from .javascript import _field_name, js_catalog

ts_catalog = Catalog(rules=js_catalog.rules + [
    NodeRule("interface_declaration", SymbolType.INTERFACE, None, _field_name("name")),
    NodeRule("type_alias_declaration", SymbolType.TYPE, None, _field_name("name")),
    NodeRule("enum_declaration", SymbolType.ENUM, None, _field_name("name")),
    NodeRule("abstract_class_declaration", SymbolType.CLASS, None, _field_name("name")),
])
