"""CLI демо: сервер стенда, хаб робота (мост, адаптер, Lua, MCP по HTTP), рабочая папка агента, моды клиента.

  uv run oc setup                 один раз: Forge, моды, конфиги, шаблон мира, карта для Navigation Upgrade
  uv run oc up [--reset]          сервер + хаб робота :8765 + рабочая папка агента; --reset заново ставит площадку
  uv run oc down                  остановить сервер и хаб робота
  uv run oc status                что запущено и что настроено
  uv run oc give <ник>            op и предметы для Navigation Upgrade игроку онлайн
  uv run oc client-mods [--dest]  скопировать моды сервера в клиент
  uv run oc workspace             пересобрать demo/workspace (скиллы и конфиги MCP для всех агентов)
  uv run oc agent <агент> [...]   запустить claude, codex или opencode в demo/workspace
  uv run oc memory [--reset]      что агент запомнил (demo/memory.db); --reset стирает память

Все команды работают из любого каталога и на любой ОС.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from adapter.robot_files import robot_commands
from demo import agent_workspace
from stand.config import Config, load_config
from stand.rcon import Rcon, RconError
from stand.server import navmap, process, setup

HUB_PID = agent_workspace.LOGS / "hub.pid"
HUB_LOG = agent_workspace.LOGS / "hub.log"
HUB_PORT = agent_workspace.HUB_PORT
# Предметы для Navigation Upgrade, кроме карты и Microchip (Tier 2): чип берётся в творческой вкладке.
NAV_ITEMS = ["gold_ingot 4", "compass 1", "potion 1 0", "crafting_table 1"]


# --- хаб: мост, адаптер, раздача Lua и MCP по HTTP -------------------------------

def hub_running(port: int = HUB_PORT) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/get.lua", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def start_hub(port: int = HUB_PORT, command: list[str] | None = None) -> bool:
    if hub_running(port):
        return False
    agent_workspace.LOGS.mkdir(parents=True, exist_ok=True)
    kwargs = {}
    if sys.platform == "win32":
        # Без своего окна консоли и без привязки к консоли, из которой вызван oc.
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    cmd = command or [sys.executable, *agent_workspace.hub_args(port)]
    with open(HUB_LOG, "ab") as log:
        proc = subprocess.Popen(cmd, cwd=agent_workspace.ROOT, stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, **kwargs)
    HUB_PID.write_text(str(proc.pid), encoding="utf-8")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if hub_running(port):
            return True
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    raise RuntimeError(f"robot hub did not start, see {HUB_LOG}")


def stop_hub() -> bool:
    if not HUB_PID.exists():
        return False
    try:
        pid = int(HUB_PID.read_text(encoding="utf-8").strip())
        os.kill(pid, signal.SIGTERM)
        stopped = True
    except (ValueError, OSError):
        stopped = False
    HUB_PID.unlink(missing_ok=True)
    return stopped


# --- проверки -------------------------------------------------------------------

def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def oc_config_state(cfg: Config) -> str:
    path = setup.oc_config_path(cfg)
    if not path.exists():
        return "missing (start the server once, stop it, run: oc setup)"
    text = path.read_text(encoding="utf-8")
    try:
        return "ok" if setup.patch_oc_config(text) == text else "not patched (stop the server, run: oc setup)"
    except ValueError as e:
        return f"unknown format: {e}"


def default_client_mods() -> Path:
    """Папка mods стандартного лаунчера (TLauncher пользуется той же)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / ".minecraft"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "minecraft"
    else:
        base = Path.home() / ".minecraft"
    return base / "mods"


# --- команды --------------------------------------------------------------------

def cmd_setup(cfg: Config, args) -> int:
    setup.setup_all(cfg, pin=args.pin)
    return 0


def cmd_up(cfg: Config, args) -> int:
    from stand.runner.reset import ensure_server

    setup.check_java(cfg)
    print("minecraft server: starting..." if not process.is_running(cfg) else "minecraft server: already running")
    ensure_server(cfg)
    print(f"minecraft server: localhost:25565 (rcon {cfg.rcon_port})")
    if args.reset:
        from stand.knowledge import KNOWLEDGE_DIR, Knowledge
        from stand.runner.run import prepare
        from stand.scenario import load_scenario

        scenario = load_scenario(agent_workspace.SCENARIO)
        prepare(cfg, scenario, Knowledge.load(KNOWLEDGE_DIR, scenario.knowledge))
        print("play area: reset, warehouse filled")
    started = start_hub()
    print(f"robot hub: {agent_workspace.HUB_URL} (MCP {agent_workspace.MCP_URL}, "
          f"{'started' if started else 'already running'})")
    print(f"agent workspace: {agent_workspace.build()}")
    print()
    print("next:")
    print("  robot shell, first time:")
    for c in robot_commands(agent_workspace.HUB_URL):
        print(f"    {c}")
    print("  agent:  uv run oc agent claude   (or codex, opencode)")
    return 0


def cmd_down(cfg: Config, args) -> int:
    print("robot hub: " + ("stopped" if stop_hub() else "was not started by oc up"))
    if process.is_running(cfg):
        process.stop_server(cfg)
        print("minecraft server: stopped")
    else:
        print("minecraft server: not running")
    return 0


def cmd_status(cfg: Config, args) -> int:
    server = process.is_running(cfg)
    map_id = navmap.find_nav_map(cfg.world_dir) if cfg.world_dir.exists() else None
    rows = [
        ("minecraft server", "running" if server else "not running (oc up)"),
        (f"robot hub :{HUB_PORT}", f"running, MCP {agent_workspace.MCP_URL}, robot: "
         f"{robot_commands(agent_workspace.HUB_URL)[0]}" if hub_running()
         else ("port busy, not the hub" if port_open(HUB_PORT) else "not running (oc up)")),
        ("opencomputers config", oc_config_state(cfg)),
        ("navigation map", f"map_{map_id}" if map_id is not None else "missing (stop the server, run: oc setup)"),
        ("agent workspace", str(agent_workspace.WS) if (agent_workspace.WS / ".mcp.json").exists()
         else "missing (oc up or oc workspace)"),
        ("agent memory", f"{agent_workspace.MEMORY_DB} (oc memory)" if agent_workspace.MEMORY_DB.exists()
         else "empty (filled by the agent)"),
    ]
    width = max(len(k) for k, _ in rows)
    for k, v in rows:
        print(f"{k:<{width}}  {v}")
    return 0 if server else 1


def cmd_give(cfg: Config, args) -> int:
    map_id = navmap.find_nav_map(cfg.world_dir)
    if map_id is None:
        print("no navigation map in the world: stop the server and run: oc setup", file=sys.stderr)
        return 1
    nick = args.nick
    try:
        with Rcon(cfg.rcon_host, cfg.rcon_port, cfg.rcon_password, timeout=10) as r:
            if nick.lower() not in r.command("list").lower():
                print(f"{nick} is not online: join localhost first", file=sys.stderr)
                return 1
            for cmd in [f"op {nick}", f"give {nick} filled_map 1 {map_id}", *(f"give {nick} {i}" for i in NAV_ITEMS)]:
                print(f"{cmd}: {r.command(cmd).strip()}")
    except RconError as e:
        print(f"server does not answer RCON ({e}): oc up", file=sys.stderr)
        return 1
    return 0


def cmd_client_mods(cfg: Config, args) -> int:
    import yaml

    dest: Path = args.dest or default_client_mods()
    mods = yaml.safe_load(cfg.mods_manifest.read_text(encoding="utf-8"))["mods"]
    missing = [m["file"] for m in mods if not (cfg.mods_cache / m["file"]).exists()]
    if missing:
        print("not in the mods cache, run oc setup first: " + ", ".join(missing), file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    wanted = {m["file"] for m in mods}
    foreign = sorted(p for p in dest.glob("*.jar") if p.name not in wanted)
    if foreign and args.move_foreign:
        aside = dest.parent / "mods-disabled"
        aside.mkdir(exist_ok=True)
        for p in foreign:
            shutil.move(str(p), aside / p.name)
        print(f"moved {len(foreign)} other jars to {aside}")
        foreign = []
    for m in mods:
        shutil.copyfile(cfg.mods_cache / m["file"], dest / m["file"])
        print(f"copied {m['file']}")
    print(f"client mods: {dest}")
    if foreign:
        print("other jars in the client mods folder (Forge 1.7.10 may refuse the server or crash on them,"
              " --move-foreign moves them to mods-disabled/):")
        for p in foreign:
            print(f"  {p.name}")
    return 0


def cmd_workspace(cfg: Config, args) -> int:
    print(f"workspace ready: {agent_workspace.build()}")
    return 0


def agent_command(agent: str, extra: list[str]) -> list[str]:
    """Команда запуска агента в demo/workspace. Claude Code и opencode берут MCP из файлов папки,
    Codex проектный конфиг в непроверенной папке не читает, поэтому сервер передаётся флагами -c."""
    from stand.runner.workspace import CODEX_TOOL_TIMEOUT_S, codex_mcp_args

    exe = shutil.which(agent)
    if exe is None:
        raise FileNotFoundError(f"{agent} is not in PATH")
    if agent == "codex":
        flags = []
        for name, spec in agent_workspace.servers().items():
            if "url" in spec:
                flags += ["-c", f"mcp_servers.{name}.url={json.dumps(spec['url'])}",
                          "-c", f"mcp_servers.{name}.tool_timeout_sec={CODEX_TOOL_TIMEOUT_S}"]
            else:
                flags += codex_mcp_args(spec, name)
        return [exe, *flags, *extra]
    return [exe, *extra]


def cmd_agent(cfg: Config, args) -> int:
    ws = agent_workspace.build()
    extra = args.extra[1:] if args.extra[:1] == ["--"] else args.extra
    cmd = agent_command(args.agent, extra)
    if not process.is_running(cfg):
        print("note: minecraft server is not running, move_to/place_at/verify_blocks need it (uv run oc up)")
    print(f"{args.agent} in {ws}")
    return subprocess.call(cmd, cwd=ws)


def memory_summary(db: Path) -> list[str]:
    """Содержимое базы памяти демо строками: закреплённые факты, места, уроки."""
    import sqlite3

    if not db.exists():
        return [f"memory is empty: {db} does not exist yet (the agent creates it on the first task)"]
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        core = con.execute("SELECT key, value FROM core ORDER BY importance DESC, key").fetchall()
        pois = con.execute("SELECT id, kind, label, item_uid, x, y, z, source FROM poi ORDER BY kind, id").fetchall()
        eps = con.execute("SELECT id, outcome, occurrences, goal, lesson FROM episode "
                          "ORDER BY last_seen_at DESC").fetchall()
    finally:
        con.close()
    out = [f"memory: {db}", f"facts ({len(core)}):"]
    out += [f"  {k} = {v}" for k, v in core]
    out.append(f"places ({len(pois)}):")
    out += [f"  poi:{i} {kind} '{label}'{' ' + uid if uid else ''} at ({x}, {y}, {z}), {src}"
            for i, kind, label, uid, x, y, z, src in pois]
    out.append(f"lessons ({len(eps)}):")
    out += [f"  ep:{i} [{outcome} x{n}] {goal}: {lesson}" for i, outcome, n, goal, lesson in eps]
    return out


def cmd_memory(cfg: Config, args) -> int:
    db = agent_workspace.MEMORY_DB
    if args.reset:
        removed = [p for p in (db, Path(f"{db}-wal"), Path(f"{db}-shm")) if p.exists()]
        for p in removed:
            p.unlink()
        print(f"memory reset: {db}" if removed else "memory was already empty")
        return 0
    print("\n".join(memory_summary(db)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="oc", description="OpenComputers robot demo on the stand server.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("setup", help="install Forge, mods, configs, world template, navigation map")
    p.add_argument("--pin", action="store_true", help="write sha256 of mods into mods.yaml")
    p = sub.add_parser("up", help="start the server, the robot hub and build the agent workspace")
    p.add_argument("--reset", action="store_true", help="reset the play area and refill the warehouse")
    sub.add_parser("down", help="stop the server and the robot hub")
    sub.add_parser("status", help="show what is running and configured")
    p = sub.add_parser("give", help="op and Navigation Upgrade items for an online player")
    p.add_argument("nick")
    p = sub.add_parser("client-mods", help="copy the server mods into the game client")
    p.add_argument("--dest", type=Path, default=None, help=f"client mods folder (default {default_client_mods()})")
    p.add_argument("--move-foreign", action="store_true", help="move other jars out of the mods folder")
    sub.add_parser("workspace", help="rebuild demo/workspace")
    p = sub.add_parser("agent", help="run an agent in demo/workspace with the robot MCP server")
    p.add_argument("agent", choices=agent_workspace.AGENTS)
    p.add_argument("extra", nargs=argparse.REMAINDER, help="arguments for the agent, e.g. -- --model haiku")
    p = sub.add_parser("memory", help="show what the agent remembers; --reset forgets everything")
    p.add_argument("--reset", action="store_true", help="delete demo/memory.db")
    args = parser.parse_args(argv)
    handlers = {"memory": cmd_memory, "setup": cmd_setup, "up": cmd_up, "down": cmd_down, "status": cmd_status, "give": cmd_give,
                "client-mods": cmd_client_mods, "workspace": cmd_workspace, "agent": cmd_agent}
    try:
        return handlers[args.cmd](load_config(), args)
    except (RuntimeError, FileNotFoundError, RconError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
