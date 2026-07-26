from __future__ import annotations

import sqlite3

from ..models.symbol import GraphEdge, Symbol

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS symbols (
      fqn TEXT, name TEXT, type TEXT, file_path TEXT,
      start_line INT, end_line INT, chunk_id TEXT, parent_id TEXT,
      PRIMARY KEY (fqn, file_path)
    )""",
    """CREATE TABLE IF NOT EXISTS edges (
      source TEXT, target TEXT, type TEXT, source_file TEXT, target_file TEXT,
      PRIMARY KEY (source, target, type, source_file)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source)",
    "CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path)",
]


class GraphStore:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path)
        for stmt in _SCHEMA:
            self._conn.execute(stmt)
        self._conn.commit()

    def upsert(self, nodes: list[Symbol], edges: list[GraphEdge]) -> None:
        files = {n.file_path for n in nodes}
        cur = self._conn.cursor()
        for file_path in files:
            cur.execute("DELETE FROM edges WHERE source_file = ? OR target_file = ?", (file_path, file_path))
            cur.execute("DELETE FROM symbols WHERE file_path = ?", (file_path,))
        for n in nodes:
            cur.execute(
                "INSERT OR REPLACE INTO symbols "
                "(fqn, name, type, file_path, start_line, end_line, chunk_id, parent_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (n.fqn, n.name, n.type, n.file_path, n.start_line, n.end_line, n.chunk_id, n.parent_id),
            )
        for e in edges:
            cur.execute(
                "INSERT OR REPLACE INTO edges "
                "(source, target, type, source_file, target_file) VALUES (?, ?, ?, ?, ?)",
                (e.source, e.target, e.type, e.source_file, e.target_file),
            )
        self._conn.commit()

    def delete_by_file(self, file_path: str) -> None:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM edges WHERE source_file = ? OR target_file = ?", (file_path, file_path))
        cur.execute("DELETE FROM symbols WHERE file_path = ?", (file_path,))
        self._conn.commit()

    def neighbors(self, fqn: str) -> dict[str, list[str]]:
        return {
            "calls": self.callees(fqn),
            "called_by": self.callers(fqn),
            "imports": self._targets(fqn, "imports"),
            "imported_by": self._sources(fqn, "imports"),
            "contains": self._targets(fqn, "contains"),
            "contained_in": self._sources(fqn, "contains"),
        }

    def callers(self, fqn: str) -> list[str]:
        return self._sources(fqn, "calls")

    def callees(self, fqn: str) -> list[str]:
        return self._targets(fqn, "calls")

    def imports_of(self, file_path: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT target FROM edges WHERE type = 'imports' AND source_file = ?", (file_path,)
        ).fetchall()
        return [r[0] for r in rows]

    def _targets(self, fqn: str, type: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT target FROM edges WHERE type = ? AND source = ?", (type, fqn)
        ).fetchall()
        return [r[0] for r in rows]

    def _sources(self, fqn: str, type: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT source FROM edges WHERE type = ? AND target = ?", (type, fqn)
        ).fetchall()
        return [r[0] for r in rows]
