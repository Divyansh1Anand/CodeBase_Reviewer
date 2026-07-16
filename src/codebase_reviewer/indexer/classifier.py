from __future__ import annotations

from pathlib import Path

EXTENSION_MAP = {
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx", ".mts": "typescript", ".cts": "typescript",
    ".py": "python", ".go": "go", ".rs": "rust", ".java": "java",
}


class FileClassifier:
    def classify(self, file_path: Path) -> str:
        return EXTENSION_MAP.get(Path(file_path).suffix, "text")
