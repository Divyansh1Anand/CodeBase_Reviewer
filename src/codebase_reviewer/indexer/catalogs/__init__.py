from __future__ import annotations

from .javascript import js_catalog
from .typescript import ts_catalog

REGISTRY = {
    "javascript": js_catalog,
    "typescript": ts_catalog,
    "tsx": ts_catalog,
}
