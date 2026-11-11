"""Схемы добавок адаптера совпадают со схемами fake-MCP (обе описывают контракт v2)."""

from adapter.tools import ADDITION_SPECS
from stand.fake_mcp.dispatch import TOOL_SPECS

ADDITIONS = {"move_to", "face", "place_at", "get_status", "verify_blocks", "search_docs", "get_action_log"}


def test_addition_specs_match_fake():
    assert set(ADDITION_SPECS) == ADDITIONS
    for name in ADDITIONS:
        assert ADDITION_SPECS[name]["inputSchema"] == TOOL_SPECS[name].schema, name
        assert ADDITION_SPECS[name]["description"] == TOOL_SPECS[name].description, name
