"""Раздаёт Lua-скрипты oc-mcp роботу по HTTP, чтобы не копировать их в сейв руками.

  python demo/serve_lua.py       (порт 8770)

На роботе (OpenOS):
  wget -f http://127.0.0.1:8770/get.lua /home/get.lua
  /home/get.lua
  oc_mcp
"""

from __future__ import annotations

import http.server
import sys
from functools import partial
from pathlib import Path

LUA_DIR = Path(__file__).resolve().parent.parent / "robot"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8770


def installer(base: str) -> bytes:
    # Только сам клиент: в robot/ ещё лежат тесты, роботу они не нужны.
    files = sorted(p.relative_to(LUA_DIR).as_posix()
                   for p in [LUA_DIR / "oc_mcp.lua", *(LUA_DIR / "oc_mcp").rglob("*.lua")])
    dirs = sorted({str(Path(f).parent.as_posix()) for f in files if "/" in f})
    lines = ['local fs = require("filesystem")', 'local shell = require("shell")']
    lines += [f'fs.makeDirectory("/home/{d}")' for d in dirs]
    lines.append("local ok = true")
    for f in files:
        lines.append(f'fs.remove("/home/{f}")')
        lines.append(f'shell.execute("wget -fq {base}/{f} /home/{f}")')
        lines.append(f'if not fs.exists("/home/{f}") then ok = false; print("FAILED {f}") end')
    lines.append(f'print(ok and "oc-mcp: {len(files)} files installed" or "oc-mcp: some files failed")')
    lines += AUTOSTART.splitlines()
    return ("\n".join(lines) + "\n").encode()


# Автозапуск: OpenOS выполняет /home/.shrc при старте шелла, то есть сразу после включения робота.
# Строка дописывается один раз, остальное содержимое .shrc не трогается.
# Остановить скрипт: Ctrl+Alt+C на роботе. Убрать автозапуск: edit /home/.shrc.
AUTOSTART = """\
local shrc = "/home/.shrc"
local text = ""
local f = io.open(shrc, "r")
if f then text = f:read("*a") or ""; f:close() end
if not text:find("oc_mcp", 1, true) then
  f = io.open(shrc, "a")
  f:write((text ~= "" and not text:find("\\n$") and "\\n" or "") .. "oc_mcp\\n")
  f:close()
  print("oc-mcp: autostart added to " .. shrc)
end
if ok then print("run now: oc_mcp   (after reboot it starts by itself)") end
"""


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] == "/get.lua":
            body = installer(f"http://{self.headers.get('Host', f'127.0.0.1:{PORT}')}")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


if __name__ == "__main__":
    print(f"serving {LUA_DIR} on http://127.0.0.1:{PORT}  (robot: wget -f http://127.0.0.1:{PORT}/get.lua /home/get.lua)")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), partial(Handler, directory=str(LUA_DIR))).serve_forever()
