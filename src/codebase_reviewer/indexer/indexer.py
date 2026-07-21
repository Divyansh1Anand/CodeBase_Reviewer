from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..models.chunk import CodeSymbol

INDEX_VERSION = "1"

_IGNORE = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__",
    "dist", "build", ".chroma", "chroma", ".idea", ".vscode",
}


@dataclass
class IndexStats:
    files_indexed: int
    files_skipped: int
    files_deleted: int
    errors: list[str]


class Indexer:
    def __init__(self, classifier, parser, walker, size_normalizer, graph_builder,
                 embedder, chroma_store, graph_store, meta_store):
        self.classifier = classifier
        self.parser = parser
        self.walker = walker
        self.size_normalizer = size_normalizer
        self.graph_builder = graph_builder
        self.embedder = embedder
        self.chroma_store = chroma_store
        self.graph_store = graph_store
        self.meta_store = meta_store

    def index(self, repo_path: Path, force: bool = False) -> IndexStats:
        repo_path = Path(repo_path)
        files_indexed = 0
        files_skipped = 0
        files_deleted = 0
        errors: list[str] = []

        current_files = list(self._walk_code_files(repo_path))
        current_paths = {str(p) for p in current_files}
        stored_paths = set(self.meta_store.get_indexed_files())

        for path_str in sorted(stored_paths - current_paths):
            try:
                self.chroma_store.delete_by_file(path_str)
                self.graph_store.delete_by_file(path_str)
                self.meta_store.remove(path_str)
                files_deleted += 1
            except Exception as exc:
                errors.append(f"{path_str}: {exc}")

        for p in current_files:
            path_str = str(p)
            try:
                content = p.read_bytes()
                content_hash = hashlib.sha256(content).hexdigest()
                if not force and self.meta_store.get_hash(path_str) == content_hash:
                    files_skipped += 1
                    continue
                source = content.decode("utf-8")
                language = self.classifier.classify(p)
                tree = self.parser.parse(source, language)
                symbols = self.walker.chunk(tree, source, path_str, language)
                symbols = self.size_normalizer.normalize(symbols)
                self._compute_fqns(symbols)
                embeddings = self.embedder.embed_texts([s.content for s in symbols])
                nodes, edges = self.graph_builder.build(symbols)
                self.chroma_store.delete_by_file(path_str)
                self.chroma_store.upsert(symbols, embeddings)
                self.graph_store.delete_by_file(path_str)
                self.graph_store.upsert(nodes, edges)
                self.meta_store.set_hash(path_str, content_hash, language)
                files_indexed += 1
            except Exception as exc:
                errors.append(f"{path_str}: {exc}")

        self.meta_store.set_version(str(repo_path), INDEX_VERSION)
        return IndexStats(files_indexed, files_skipped, files_deleted, errors)

    def _compute_fqns(self, symbols: list[CodeSymbol]) -> None:
        by_id = {s.id: s for s in symbols}
        for s in symbols:
            if s.name is None:
                s.fqn = None
                continue
            parts: list[str] = []
            cur = s
            seen: set[str] = set()
            while cur is not None and cur.id not in seen:
                seen.add(cur.id)
                if cur.name is not None:
                    parts.append(cur.name)
                cur = by_id.get(cur.parent_id) if cur.parent_id is not None else None
            s.fqn = ".".join(reversed(parts))

    def _walk_code_files(self, repo_path: Path):
        for p in sorted(repo_path.rglob("*")):
            if not p.is_file():
                continue
            relative = p.relative_to(repo_path)
            if any(part in _IGNORE for part in relative.parts):
                continue
            if self.classifier.classify(p) == "text":
                continue
            yield p
