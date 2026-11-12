"""Upstream: адаптер говорит с настоящим мостом oc-mcp, робота изображает RobotDouble."""

import anyio
from adapter_harness import bridge, make_sim


def test_call_roundtrip(tmp_path):
    sim = make_sim(inventory=[{"item": "minecraft:cobblestone", "count": 9}])

    async def go():
        async with bridge(sim, tmp_path) as up:
            return await up.call("inventory_scan", {})

    assert anyio.run(go) == (True, sim.inventory_scan()["message"], None)


def test_bridge_bad_argument(tmp_path):
    async def go():
        async with bridge(make_sim(), tmp_path) as up:
            return await up.call("move", {})

    assert anyio.run(go) == (False, "bad argument: direction is required", "BLOCKED")


def test_robot_error_comes_back_with_code(tmp_path):
    async def go():
        async with bridge(make_sim(), tmp_path) as up:
            return await up.call("swing", {"side": "front"})

    assert anyio.run(go) == (False, "nothing to hit on front (air)", "BLOCKED")


def test_robot_error_is_tool_result(tmp_path):
    async def go():
        async with bridge(make_sim(), tmp_path) as up:
            return await up.session.call_tool("swing", {"side": "front"})

    result = anyio.run(go)
    assert result.is_error and result.structured_content == {"error_code": "BLOCKED"}


def test_list_tools_has_oc_mcp_tools(tmp_path):
    async def go():
        async with bridge(make_sim(), tmp_path) as up:
            return await up.list_tools()

    tools = {t["name"]: t for t in anyio.run(go)}
    assert len(tools) == 21 and "place" in tools
    assert tools["move"]["inputSchema"]["required"] == ["direction"]

