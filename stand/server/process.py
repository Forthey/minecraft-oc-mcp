"""Запуск, остановка и проверка состояния сервера Minecraft."""

from __future__ import annotations

import os
import subprocess
import sys
import time

from stand.config import Config
from stand.rcon import Rcon, RconError

PID_FILE = "stand.pid"
CONSOLE_LOG = "stand-console.log"


def forge_jar(cfg: Config):
    """Возвращает путь к universal jar Forge в папке сервера или None."""
    jars = sorted(cfg.server_dir.glob("forge-1.7.10-*-universal.jar"))
    return jars[-1] if jars else None


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True
        ).stdout
        return str(pid) in out
    # Если сервер запущен этим же процессом, после выхода он остаётся зомби и
    # os.kill его ещё видит. waitpid забирает статус и убирает зомби.
    try:
        reaped, _ = os.waitpid(pid, os.WNOHANG)
        if reaped == pid:
            return False
    except ChildProcessError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_pid(cfg: Config) -> int | None:
    path = cfg.server_dir / PID_FILE
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except ValueError:
        return None


def is_running(cfg: Config) -> bool:
    """Сервер считается запущенным, если отвечает по RCON."""
    try:
        with Rcon(cfg.rcon_host, cfg.rcon_port, cfg.rcon_password, timeout=2.0) as rcon:
            rcon.command("list")
        return True
    except RconError:
        return False


def start_server(cfg: Config) -> subprocess.Popen:
    """Запускает сервер в фоне. Процесс переживает завершение вызывающего скрипта."""
    jar = forge_jar(cfg)
    if jar is None:
        raise FileNotFoundError(
            f"Forge universal jar not found in {cfg.server_dir}, run `python -m stand.server setup`"
        )
    log = open(cfg.server_dir / CONSOLE_LOG, "ab")
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        [cfg.java_path, *cfg.java_args, "-jar", jar.name, "nogui"],
        cwd=cfg.server_dir,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        **kwargs,
    )
    (cfg.server_dir / PID_FILE).write_text(str(proc.pid))
    return proc


def wait_rcon(cfg: Config, timeout: float = 180, proc: subprocess.Popen | None = None) -> None:
    """Ждёт, пока сервер начнёт отвечать по RCON.

    Если передан proc, его завершение замечается через poll(). Без этого упавший
    дочерний процесс остаётся зомби и по pid выглядит живым. Бросает RconError,
    если процесс завершился или вышел таймаут.
    """
    deadline = time.monotonic() + timeout
    pid = _read_pid(cfg)
    while time.monotonic() < deadline:
        if is_running(cfg):
            return
        exited = proc.poll() is not None if proc is not None else (
            pid is not None and not _pid_alive(pid)
        )
        if exited:
            raise RconError(
                f"server process exited, see {cfg.server_dir / CONSOLE_LOG}"
            )
        time.sleep(2)
    raise RconError(f"server did not answer RCON within {timeout:.0f} s")


def stop_server(cfg: Config, timeout: float = 90) -> None:
    """Останавливает сервер командой stop и ждёт завершения процесса."""
    pid = _read_pid(cfg)
    try:
        with Rcon(cfg.rcon_host, cfg.rcon_port, cfg.rcon_password) as rcon:
            rcon.command("stop")
    except RconError:
        pass
    deadline = time.monotonic() + timeout
    while pid is not None and _pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(1)
    if pid is not None and _pid_alive(pid):
        raise RuntimeError(f"server process {pid} did not stop within {timeout:.0f} s")
    (cfg.server_dir / PID_FILE).unlink(missing_ok=True)
