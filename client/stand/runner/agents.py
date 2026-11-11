"""Шаблоны агентов и запуск агента с таймаутом и убийством дерева процессов."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

AGENTS_PATH = Path(__file__).resolve().parents[1] / "agents.yaml"
KILL_GRACE_S = 5


@dataclass
class AgentCfg:
    """Запись из agents.yaml."""

    name: str
    cmd: list[str]
    skills_dir: str | None
    mcp_format: str
    usage_parser: str
    env: dict = field(default_factory=dict)


@dataclass
class AgentRun:
    """Итог запуска агента."""

    exit_code: int | None
    timed_out: bool
    duration_s: float


def load_agents(path: Path = AGENTS_PATH) -> dict[str, AgentCfg]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        name: AgentCfg(
            name=name,
            cmd=[str(c) for c in a["cmd"]],
            skills_dir=a.get("skills_dir"),
            mcp_format=a["mcp_format"],
            usage_parser=a.get("usage_parser", "none"),
            env=dict(a.get("env") or {}),
        )
        for name, a in data.items()
    }


def render_cmd(
    a: AgentCfg,
    prompt: str,
    mcp_config: Path | None,
    workspace: Path,
    mcp_args: list[str] | None = None,
    scenario_dir: Path | None = None,
) -> list[str]:
    """Подставляет значения в шаблон команды. Первый элемент ищется в PATH.

    {python} это интерпретатор стенда, так агент-скрипт получает те же зависимости.
    Части с путями вида "{scenario_dir}/script.json" нормализуются под ОС.
    """
    values = {
        "{prompt}": prompt,
        "{mcp_config}": str(mcp_config) if mcp_config else "",
        "{workspace}": str(workspace),
        "{scenario_dir}": str(scenario_dir) if scenario_dir else "",
        "{python}": sys.executable,
    }
    path_keys = ("{workspace}", "{scenario_dir}")
    out: list[str] = []
    for part in a.cmd:
        if part == "{mcp_args}":
            out.extend(mcp_args or [])
            continue
        is_path = any(k in part for k in path_keys) and part not in path_keys
        for key, val in values.items():
            part = part.replace(key, val)
        out.append(os.path.normpath(part) if is_path else part)
    exe = shutil.which(out[0])
    if exe is None:
        raise FileNotFoundError(f"agent executable {out[0]} not found in PATH")
    out[0] = exe
    return out


def render_env(a: AgentCfg) -> dict[str, str]:
    """Переменные окружения агента. {root} заменяется на корень репозитория."""
    root = str(AGENTS_PATH.parents[1])
    return {k: str(v).replace("{root}", root) for k, v in a.env.items()}


def _kill_tree(proc: subprocess.Popen) -> None:
    """Убивает агента и всех его потомков."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        # Агент запущен в новой сессии, поэтому номер его группы равен его pid.
        # SIGTERM даёт шанс завершиться аккуратно, SIGKILL добивает оставшихся потомков.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                break
            if sig == signal.SIGTERM:
                time.sleep(KILL_GRACE_S)
    try:
        proc.wait(timeout=KILL_GRACE_S)
    except subprocess.TimeoutExpired:
        pass


def run_agent(
    cmd: list[str],
    cwd: Path,
    timeout_s: float,
    transcript: Path,
    stderr_log: Path,
    env: dict | None = None,
) -> AgentRun:
    """Запускает агента, stdout пишет в transcript, stderr в stderr_log.

    По таймауту убивает всё дерево процессов: на Windows через taskkill /T, на
    POSIX через группу процессов (агент запускается в новой сессии).
    """
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    transcript.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with open(transcript, "wb") as out, open(stderr_log, "wb") as err:
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            env={**os.environ, **(env or {})}, **kwargs,
        )
        try:
            code = proc.wait(timeout=timeout_s)
            timed_out = False
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            code = proc.poll()
            timed_out = True
    return AgentRun(code, timed_out, time.monotonic() - start)
