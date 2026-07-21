from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Finding:
    severity: str
    file_path: str | None
    line_range: tuple[int, int] | None
    description: str
    suggestion: str | None


@dataclass
class ReviewResult:
    summary: str
    findings: list[Finding]
    raw: str
