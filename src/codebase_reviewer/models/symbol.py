from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GraphEdge:
    source: str
    target: str
    type: str
    source_file: str
    target_file: str


@dataclass
class Symbol:
    fqn: str
    name: str | None
    type: str
    file_path: str
    start_line: int
    end_line: int
    chunk_id: str
    parent_id: str | None
