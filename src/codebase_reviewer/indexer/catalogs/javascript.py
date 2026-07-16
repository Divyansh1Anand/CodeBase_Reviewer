from __future__ import annotations

from ...models.chunk import SymbolType
from .base import Catalog, NodeRule

_FUNCTION_VALUE_TYPES = {"arrow_function", "function_expression", "generator_function"}


def _field_name(field: str):
    def extract(node):
        child = node.child_by_field_name(field)
        return child.text.decode("utf-8") if child is not None else None
    return extract


def _no_name(node):
    return None


def _parent_is_lexical(node):
    return node.parent is not None and node.parent.type == "lexical_declaration"


def _parent_is_variable_declaration(node):
    return node.parent is not None and node.parent.type == "variable_declaration"


def _declarator_value_is_function(node):
    value = node.child_by_field_name("value")
    return value is not None and value.type in _FUNCTION_VALUE_TYPES


def _lexical_function(node):
    return _parent_is_lexical(node) and _declarator_value_is_function(node)


js_catalog = Catalog(rules=[
    NodeRule("function_declaration", SymbolType.FUNCTION, None, _field_name("name")),
    NodeRule("generator_function_declaration", SymbolType.FUNCTION, None, _field_name("name")),
    NodeRule("variable_declarator", SymbolType.FUNCTION, _lexical_function, _field_name("name")),
    NodeRule("variable_declarator", SymbolType.CONSTANT, _parent_is_lexical, _field_name("name")),
    NodeRule("variable_declarator", SymbolType.VARIABLE, _parent_is_variable_declaration, _field_name("name")),
    NodeRule("class_declaration", SymbolType.CLASS, None, _field_name("name")),
    NodeRule("method_definition", SymbolType.METHOD, None, _field_name("name")),
    NodeRule("export_statement", SymbolType.EXPORT, None, _no_name),
    NodeRule("import_statement", SymbolType.IMPORT, None, _no_name),
])
