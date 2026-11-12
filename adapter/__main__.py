"""CLI адаптера: MCP-сервер контракта v2.

python -m adapter serve [--host 127.0.0.1] [--port 8765] [--world-id ID] [--log action_log.jsonl]
                        [--bridge-log PATH] [--map module:factory --map-arg key=value ...]
    Долгоживущий процесс: на одном порту HTTP для робота (/poll, /result), раздача Lua (/get.lua)
    и MCP streamable HTTP (/mcp) для любого числа клиентов.

python -m adapter --in-process [--port 8765] [...]
    MCP по stdio, мост в том же процессе, тот же HTTP-сервер для робота и Lua.

python -m adapter --oc-mcp <oc-mcp>/bridge/server.py [--port 8765] [...]
    MCP по stdio, мост дочерним процессом (старый режим).

stdout в stdio-режимах занят протоколом MCP, диагностика идёт в stderr.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys
import tempfile
from pathlib import Path

import anyio
from mcp.server.stdio import stdio_server

from adapter import hub
from adapter.action_log import ActionLog
from adapter.explored_map import ExploredMap
from adapter.java_pathfinding import JavaPathfinder
from adapter.memory_link import MemoryLink
from adapter.robot import RobotAdapter
from adapter.server import make_server
from adapter.upstream import Upstream, bridge_cmd
from adapter.worldmap import NoMap


def load_link(args):
    if not args.memory_db and not os.environ.get("MEMORY_DB"):
        return None
    return MemoryLink(args.world_id or "default", db_path=args.memory_db)


def load_map(spec: str | None, args: list[str], explore_db=None, world_id=None, link=None):
    if not spec and explore_db:
        return ExploredMap(world_id or "default", explore_db, hazards=link)
    if not spec:
        return NoMap()
    module_name, _, factory = spec.partition(":")
    kwargs = dict(a.split("=", 1) for a in args)
    return getattr(importlib.import_module(module_name), factory)(**kwargs)


def load_pathfinder(args):
    if not args.pf_jar:
        return None
    if not args.pf_world:
        raise SystemExit("--pf-jar needs --pf-world (path to the world save)")
    return JavaPathfinder(args.pf_jar, args.pf_world, args.pf_java, long_range=args.long_range)


def make_adapter(up, args) -> RobotAdapter:
    link = load_link(args)
    worldmap = load_map(args.map, args.map_arg, args.explore_db, args.world_id, link)
    return RobotAdapter(up, worldmap, ActionLog(args.log), load_pathfinder(args), link)


def bridge_log(args) -> Path:
    return args.bridge_log or Path(tempfile.gettempdir()) / f"oc-mcp-bridge-{args.port}.log"


def build_bridge_cmd(args) -> list[str]:
    return bridge_cmd(Path(args.oc_mcp), args.python, args.port, bridge_log(args), args.world_id)


def _local(args):
    bridge = hub.make_bridge(args.host, args.port, bridge_log(args), args.world_id)
    adapter = make_adapter(hub.LocalUpstream(bridge), args)
    return bridge, adapter, make_server(adapter, bridge.list_tools())


async def _serve_http(args) -> None:
    bridge, _, server = _local(args)
    print(f"oc-mcp hub on http://{args.host}:{args.port}: MCP /mcp, robot /poll, installer /get.lua",
          file=sys.stderr, flush=True)
    await hub.serve_http(hub.make_app(server, bridge, args.host), args.host, args.port)


async def _serve_in_process(args) -> None:
    bridge, _, server = _local(args)
    http = hub.http_server(hub.make_app(server, bridge, args.host), args.host, args.port)
    async with anyio.create_task_group() as tg:
        tg.start_soon(http.serve)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
        http.should_exit = True


async def _serve_child(args) -> None:
    async with Upstream(build_bridge_cmd(args)) as up:
        adapter = make_adapter(up, args)
        server = make_server(adapter, await up.list_tools())
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host for the robot (and MCP in serve)")
    parser.add_argument("--port", type=int, default=hub.DEFAULT_PORT, help="HTTP port the robot polls")
    parser.add_argument("--bridge-log", type=Path, default=None,
                        help="bridge log file (default: oc-mcp-bridge-<port>.log in the temp dir)")
    parser.add_argument("--world-id", default=None, help="world id for world_info")
    parser.add_argument("--log", type=Path, default=None, help="action log JSONL path")
    parser.add_argument("--map", default=None, help="world map plugin, module:factory")
    parser.add_argument("--map-arg", action="append", default=[], help="key=value for the map plugin")
    parser.add_argument("--pf-jar", default=None, help="Java pathfinding jar for long-range move_to")
    parser.add_argument("--pf-world", default=None, help="world save directory read by the Java pathfinding")
    parser.add_argument("--pf-java", default="java", help="java 17+ executable for the pathfinding jar")
    parser.add_argument("--explore-db", type=Path, default=None,
                        help="SQLite file of the map the robot explores itself (used when --map is not set)")
    parser.add_argument("--memory-db", type=Path, default=None,
                        help="memory-mcp database for hazards and waypoints (default: $MEMORY_DB)")
    parser.add_argument("--long-range", type=int, default=0,
                        help="move_to farther than this (blocks along any axis) uses the Java pathfinding; 0 = always")


def serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m adapter serve",
                                     description="Long-running hub: robot HTTP, Lua installer, MCP over HTTP.")
    _common(parser)
    return parser


def main_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m adapter", description="MCP contract v2 on top of oc-mcp.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--oc-mcp", help="path to oc-mcp bridge/server.py, run as a child process")
    mode.add_argument("--in-process", action="store_true", help="run the bridge in this process")
    parser.add_argument("--python", default=sys.executable, help="python to run oc-mcp (3.11+)")
    _common(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    if argv[:1] == ["serve"]:
        anyio.run(_serve_http, serve_parser().parse_args(argv[1:]))
        return 0
    args = main_parser().parse_args(argv)
    anyio.run(_serve_in_process if args.in_process else _serve_child, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
