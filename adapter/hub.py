from __future__ import annotations

import json
import sys
from pathlib import Path

import anyio
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from adapter import robot_files

BRIDGE_DIR = Path(__file__).resolve().parent.parent / "bridge"
DEFAULT_PORT = 8765


def load_bridge_module():
    if str(BRIDGE_DIR) not in sys.path:
        sys.path.insert(0, str(BRIDGE_DIR))
    import core
    import tools

    return core, tools


def make_bridge(host: str = "127.0.0.1", port: int = DEFAULT_PORT, log_file: Path | None = None,
                world_id: str | None = None):
    core, tools = load_bridge_module()
    return core.Bridge(tools.TOOLS, host=host, port=port, log_file=log_file, world_id=world_id)


class LocalUpstream:
    def __init__(self, bridge):
        self.bridge = bridge
        self._argument_error = load_bridge_module()[0].ArgumentError

    async def call(self, name: str, args: dict) -> tuple[bool, str, str | None]:
        try:
            return await anyio.to_thread.run_sync(self.bridge.run_tool, name, args)
        except self._argument_error as e:
            return False, f"bad argument: {e}", "BLOCKED"

    async def list_tools(self) -> list[dict]:
        return self.bridge.list_tools()


def robot_routes(bridge, default_url: str) -> list[Route]:
    async def poll(request: Request) -> Response:
        bridge.log("GET /poll")
        return JSONResponse({"command": bridge.next_command()})

    async def result(request: Request) -> Response:
        body = (await request.body()).decode(errors="replace")
        bridge.log(f"POST /result {body[:200]}")
        try:
            data = json.loads(body)
            data["id"]
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"error": "invalid result"}, status_code=400)
        bridge.store_result(data)
        return JSONResponse({"ok": True})

    async def get_lua(request: Request) -> Response:
        base = f"http://{request.headers.get('host') or request.url.netloc}"
        url = None if base == default_url else base
        return PlainTextResponse(robot_files.installer(base, url))

    async def lua(request: Request) -> Response:
        body = robot_files.lua_file(request.path_params["path"])
        if body is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        return PlainTextResponse(body)

    return [
        Route("/poll", poll, methods=["GET"]),
        Route("/result", result, methods=["POST"]),
        Route("/get.lua", get_lua, methods=["GET"]),
        Route("/{path:path}", lua, methods=["GET"]),
    ]


def make_app(server, bridge, host: str):
    return server.streamable_http_app(
        host=host,
        custom_starlette_routes=robot_routes(bridge, f"http://127.0.0.1:{DEFAULT_PORT}"),
    )


def http_server(app, host: str, port: int):
    import uvicorn

    config = uvicorn.Config(app, host=host, port=port, log_config=None, access_log=False, log_level="warning",
                            lifespan="on")
    return uvicorn.Server(config)


async def serve_http(app, host: str, port: int) -> None:
    await http_server(app, host, port).serve()
