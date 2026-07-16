from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum


class SymbolType(str, Enum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    TYPE = "type"

    IMPORT = "import"
    EXPORT = "export"
    REEXPORT = "reexport"
    CONSTANT = "constant"
    VARIABLE = "variable"

    IF_BLOCK = "if_block"
    LOOP_BLOCK = "loop_block"
    TRY_BLOCK = "try_block"

    STATEMENT = "statement"

    TEXT = "text"


@dataclass
class CodeSymbol:
    id: str
    parent_id: str | None
    name: str | None
    type: SymbolType
    fqn: str | None
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str

    @staticmethod
    def make_id(file_path: str, start_line: int, end_line: int, type: SymbolType) -> str:
        key = f"{file_path}:{start_line}:{end_line}:{type.value}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()
