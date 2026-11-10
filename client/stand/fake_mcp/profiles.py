"""Профили возможностей fake-MCP: какие tools отключены.

Нужны, чтобы проверить агента при другом наборе возможностей робота, например
если зрения в мире не будет или RAG по документации не появится.
"""

from __future__ import annotations

PROFILES: dict[str, set[str]] = {
    "full": set(),
    "no-vision": {"inspect", "scan_area", "get_known_map"},
    "no-docs": {"search_docs"},
}
