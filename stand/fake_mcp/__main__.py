"""Fake-MCP как stdio MCP-сервер.

python -m stand.fake_mcp --scenario <scenario.yaml> --log <action_log.jsonl>
                         [--profile full|no-vision|no-docs] [--world rcon|memory]

stdout занят протоколом MCP, поэтому диагностика идёт только в stderr.
Ответ каждого tool это один TextContent с JSON конверта {ok, error_code?, message, data}.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from stand.config import load_config
from stand.fake_mcp.action_log import ActionLog
from stand.fake_mcp.dispatch import TOOL_SPECS, Dispatcher
from stand.fake_mcp.sim import RobotSim
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.rcon import ReconnectingRcon
from stand.scenario import load_scenario
from stand.world.backend import MemoryWorld, RconWorld

def build_dispatcher(scenario_path: Path, log_path: Path | None, profile: str | None, world: str) -> Dispatcher:
    """Собирает диспетчер по сценарию. Отдельно от main, чтобы тесты могли его вызвать."""
    s = load_scenario(scenario_path)
    k = Knowledge.load(KNOWLEDGE_DIR, s.knowledge)
    if world == "memory":
        backend = MemoryWorld(s.scene_blocks())
    else:
        cfg = load_config()
        rcon = ReconnectingRcon(cfg.rcon_host, cfg.rcon_port, cfg.rcon_password, timeout=10)
        rcon.connect()
        backend = RconWorld(rcon)
    sim = RobotSim(s, k, backend)
    return Dispatcher(sim, profile or s.profile, s.faults, ActionLog(log_path))


def make_server(dispatcher: Dispatcher) -> Server:
    """MCP-сервер поверх диспетчера."""

    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        tools = [
            types.Tool(name=name, description=TOOL_SPECS[name].description, input_schema=TOOL_SPECS[name].schema)
            for name in dispatcher.enabled_tools()
        ]
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        env = dispatcher.call(params.name, params.arguments or {})
        text = json.dumps(env, ensure_ascii=False)
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=False)

    return Server(
        "oc-robot-fake",
        version="0.1",
        instructions="Fake OpenComputers robot for the e2e stand. Tools follow the robot MCP contract.",
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def _serve(server: Server) -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m stand.fake_mcp")
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--log", type=Path, default=None, help="action log JSONL path")
    parser.add_argument("--profile", default=None, help="override the scenario profile")
    parser.add_argument("--world", choices=["rcon", "memory"], default="rcon")
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    dispatcher = build_dispatcher(args.scenario, args.log, args.profile, args.world)
    anyio.run(_serve, make_server(dispatcher))
    return 0


if __name__ == "__main__":
    sys.exit(main())
