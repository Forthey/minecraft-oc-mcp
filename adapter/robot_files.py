from __future__ import annotations

from pathlib import Path

LUA_DIR = Path(__file__).resolve().parent.parent / "robot"

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


def robot_commands(base: str) -> list[str]:
    return [f"wget -f {base}/get.lua /home/get.lua", "/home/get.lua"]


def client_files() -> list[str]:
    return sorted(p.relative_to(LUA_DIR).as_posix()
                  for p in [LUA_DIR / "oc_mcp.lua", *(LUA_DIR / "oc_mcp").rglob("*.lua")])


def installer(base: str, bridge_url: str | None = None) -> bytes:
    files = client_files()
    dirs = sorted({str(Path(f).parent.as_posix()) for f in files if "/" in f})
    lines = ['local fs = require("filesystem")', 'local shell = require("shell")']
    lines += [f'fs.makeDirectory("/home/{d}")' for d in dirs]
    lines.append("local ok = true")
    for f in files:
        lines.append(f'fs.remove("/home/{f}")')
        lines.append(f'shell.execute("wget -fq {base}/{f} /home/{f}")')
        lines.append(f'if not fs.exists("/home/{f}") then ok = false; print("FAILED {f}") end')
    lines.append(f'print(ok and "oc-mcp: {len(files)} files installed" or "oc-mcp: some files failed")')
    autostart = AUTOSTART
    if bridge_url:
        autostart = autostart.replace('"oc_mcp\\n"', f'"oc_mcp {bridge_url}\\n"').replace(
            "run now: oc_mcp ", f"run now: oc_mcp {bridge_url} ")
    lines += autostart.splitlines()
    return ("\n".join(lines) + "\n").encode()


def lua_file(path: str) -> bytes | None:
    rel = path.lstrip("/")
    if rel not in client_files():
        return None
    return (LUA_DIR / rel).read_bytes()
