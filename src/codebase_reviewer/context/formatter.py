from __future__ import annotations

from ..models.chunk import CodeSymbol

_FENCE = {
    "javascript": "javascript",
    "typescript": "typescript",
    "tsx": "tsx",
    "python": "python",
}


def _lang_fence(language: str) -> str:
    return _FENCE.get(language, "")


def _format(symbol: CodeSymbol) -> str:
    fence = _lang_fence(symbol.language)
    name = symbol.fqn if symbol.fqn is not None else "(anonymous)"
    header = (
        f"// File: {symbol.file_path}:{symbol.start_line}-{symbol.end_line}\n"
        f"// Symbol: {name} ({symbol.type.value})"
    )
    return f"{header}\n\n```{fence}\n{symbol.content}\n```"
