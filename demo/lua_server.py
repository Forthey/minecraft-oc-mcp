"""Раздаёт Lua-скрипты oc-mcp роботу по HTTP отдельно от моста.

Обычно не нужен: `python -m adapter serve` раздаёт их сам на порту моста (8765).

  uv run python -m demo.lua_server [--port 8770]

На роботе (OpenOS):
  wget -f http://127.0.0.1:8770/get.lua /home/get.lua
  /home/get.lua
  oc_mcp
"""

from __future__ import annotations

import argparse
import http.server
import sys
from functools import partial

from adapter import robot_files
from adapter.robot_files import LUA_DIR

DEFAULT_PORT = 8770


def robot_commands(port: int = DEFAULT_PORT) -> list[str]:
    return robot_files.robot_commands(f"http://127.0.0.1:{port}")


def installer(base: str) -> bytes:
    return robot_files.installer(base)


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] == "/get.lua":
            host = self.headers.get("Host") or f"127.0.0.1:{self.server.server_address[1]}"
            body = installer(f"http://{host}")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def serve(port: int = DEFAULT_PORT) -> None:
    print(f"serving {LUA_DIR} on http://127.0.0.1:{port}  (robot: {'; '.join(robot_commands(port))})", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(LUA_DIR))).serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m demo.lua_server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve(parser.parse_args(argv).port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
