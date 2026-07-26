from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS indexed_files (
      file_path TEXT PRIMARY KEY,
      content_hash TEXT,
      indexed_at TIMESTAMP,
      language TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS index_state (
      repo_path TEXT PRIMARY KEY,
      version TEXT,
      last_indexed TIMESTAMP
    )""",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MetaStore:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path)
        for stmt in _SCHEMA:
            self._conn.execute(stmt)
        self._conn.commit()

    def get_hash(self, file_path: str) -> str | None:
        row = self._conn.execute(
            "SELECT content_hash FROM indexed_files WHERE file_path = ?", (file_path,)
        ).fetchone()
        return row[0] if row is not None else None

    def set_hash(self, file_path: str, content_hash: str, language: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO indexed_files (file_path, content_hash, indexed_at, language) "
            "VALUES (?, ?, ?, ?)",
            (file_path, content_hash, _now(), language),
        )
        self._conn.commit()

    def get_indexed_files(self) -> list[str]:
        rows = self._conn.execute("SELECT file_path FROM indexed_files").fetchall()
        return [r[0] for r in rows]

    def remove(self, file_path: str) -> None:
        self._conn.execute("DELETE FROM indexed_files WHERE file_path = ?", (file_path,))
        self._conn.commit()

    def get_version(self, repo_path: str) -> str | None:
        row = self._conn.execute(
            "SELECT version FROM index_state WHERE repo_path = ?", (repo_path,)
        ).fetchone()
        return row[0] if row is not None else None

    def set_version(self, repo_path: str, version: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO index_state (repo_path, version, last_indexed) VALUES (?, ?, ?)",
            (repo_path, version, _now()),
        )
        self._conn.commit()
