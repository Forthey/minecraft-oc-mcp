"""Схемы добавок адаптера совпадают со схемами fake-MCP (обе описывают контракт v2)."""

from adapter.tools import ADDITION_SPECS
from stand.fake_mcp.dispatch import TOOL_SPECS

ADDITIONS = {"move_to", "face", "place_at", "get_status", "verify_blocks", "search_docs", "get_action_log"}


def test_addition_specs_match_fake():
    assert set(ADDITION_SPECS) == ADDITIONS
    for name in ADDITIONS:
        assert ADDITION_SPECS[name]["inputSchema"] == TOOL_SPECS[name].schema, name
        assert ADDITION_SPECS[name]["description"] == TOOL_SPECS[name].description, name


def _args(schema: dict) -> tuple[dict, set]:
    """Аргументы схемы без описаний и значений по умолчанию, Optional раскрыт до самого типа."""
    out = {}
    for name, prop in schema.get("properties", {}).items():
        if "anyOf" in prop:
            prop = next(p for p in prop["anyOf"] if p.get("type") != "null")
        out[name] = {k: v for k, v in prop.items() if k not in ("description", "title", "default")}
    return out, set(schema.get("required", []))


def test_fake_schemas_match_oc_mcp():
    """fake-MCP принимает ровно те аргументы tools oc-mcp, что и настоящий мост."""
    import importlib.util
    import sys

    from adapter_harness import oc_mcp_server

    # Имя tools занято пакетом tools/ репозитория, поэтому модуль грузится по пути под своим именем.
    bridge_dir = oc_mcp_server().parent
    spec = importlib.util.spec_from_file_location("oc_mcp_tools", bridge_dir / "tools.py")
    oc_tools = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(bridge_dir))
    try:
        spec.loader.exec_module(oc_tools)
    finally:
        sys.path.pop(0)
    oc = {t.name: t.schema() for t in oc_tools.TOOLS}
    assert set(oc) | ADDITIONS == set(TOOL_SPECS)
    for name, schema in oc.items():
        assert _args(TOOL_SPECS[name].schema) == _args(schema), name
