from __future__ import annotations

from tree_sitter import Language, Parser, Tree

import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts

_GRAMMARS = {
    "javascript": tsjs.language,
    "typescript": tsts.language_typescript,
    "tsx": tsts.language_tsx,
}


class CodeParser:
    def __init__(self) -> None:
        self._languages: dict[str, Language] = {}

    def _get_language(self, language: str) -> Language:
        if language not in _GRAMMARS:
            raise ValueError(f"No tree-sitter grammar available for language: {language!r}")
        if language not in self._languages:
            self._languages[language] = Language(_GRAMMARS[language]())
        return self._languages[language]

    def parse(self, source: str, language: str) -> Tree:
        parser = Parser(self._get_language(language))
        return parser.parse(bytes(source, "utf-8"))
