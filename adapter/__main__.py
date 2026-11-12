"""CLI адаптера: MCP-сервер контракта v2 поверх oc-mcp.

python -m adapter --oc-mcp <oc-mcp>/bridge/server.py [--port 8765] [--bridge-log PATH]
                  [--world-id ID] [--log action_log.jsonl]
                  [--map module:factory --map-arg key=value ...]

stdout занят протоколом MCP, диагностика идёт в stderr. oc-mcp запускается дочерним
процессом, его мост слушает --port для робота.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
import tempfile
from pathlib import Path

import anyio
from mcp.server.stdio import stdio_server

from adapter.action_log import ActionLog
from adapter.robot import RobotAdapter
from adapter.server import make_server
from adapter.upstream import Upstream, bridge_cmd
from adapter.worldmap import NoMap


def load_map(spec: str | None, args: list[str]):
    """Карта из плагина "module:factory" с аргументами key=value. Без плагина NoMap."""
    if not spec:
        return NoMap()
    module_name, _, factory = spec.partition(":")
    kwargs = dict(a.split("=", 1) for a in args)
    return getattr(importlib.import_module(module_name), factory)(**kwargs)


def build_bridge_cmd(args) -> list[str]:
    """Команда моста oc-mcp. Лог моста по умолчанию во временной папке, не в репозитории oc-mcp."""
    log = args.bridge_log or Path(tempfile.gettempdir()) / f"oc-mcp-bridge-{args.port}.log"
    return bridge_cmd(Path(args.oc_mcp), args.python, args.port, log, args.world_id)


async def _serve(args) -> None:
    async with Upstream(build_bridge_cmd(args)) as up:
        # Позиция робота читается лениво при первой добавке: initialize отвечаем сразу,
        # даже если робот ещё не опрашивает мост.
        adapter = RobotAdapter(up, load_map(args.map, args.map_arg), ActionLog(args.log))
        server = make_server(adapter, await up.list_tools())
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())


def main_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m adapter", description="MCP contract v2 on top of oc-mcp.")
    parser.add_argument("--oc-mcp", required=True, help="path to oc-mcp bridge/server.py")
    parser.add_argument("--python", default=sys.executable, help="python to run oc-mcp (3.11+)")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port the robot polls")
    parser.add_argument("--bridge-log", type=Path, default=None,
                        help="oc-mcp bridge log file (default: oc-mcp-bridge-<port>.log in the temp dir)")
    parser.add_argument("--world-id", default=None, help="world id for world_info")
    parser.add_argument("--log", type=Path, default=None, help="action log JSONL path")
    parser.add_argument("--map", default=None, help="world map plugin, module:factory")
    parser.add_argument("--map-arg", action="append", default=[], help="key=value for the map plugin")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = main_parser().parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    anyio.run(_serve, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
