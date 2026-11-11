"""MCP-сервер адаптера для агента: tools oc-mcp и добавки, ответ это JSON конверта."""

from __future__ import annotations

import json

import mcp_types as types
from mcp.server.lowlevel import Server

from adapter.robot import RobotAdapter
from adapter.tools import ADDITION_SPECS


def make_server(adapter: RobotAdapter, upstream_tools: list[dict]) -> Server:
    """Сервер поверх RobotAdapter. upstream_tools это list_tools oc-mcp."""
    specs = {t["name"]: t for t in upstream_tools}
    specs.update({name: {"name": name, **spec} for name, spec in ADDITION_SPECS.items()})

    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        tools = [types.Tool(name=name, description=s["description"], input_schema=s["inputSchema"])
                 for name, s in specs.items()]
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        env = await adapter.call(params.name, params.arguments or {})
        text = json.dumps(env, ensure_ascii=False)
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=False)

    return Server(
        "oc-robot-adapter",
        version="0.1",
        instructions="OpenComputers robot via oc-mcp. Tools follow the robot MCP contract v2.",
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )
