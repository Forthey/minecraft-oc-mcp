"""Общий код тестов адаптера: настоящий мост oc-mcp и тестовый робот на RobotSim."""

from __future__ import annotations

import copy
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from adapter.upstream import Upstream, bridge_cmd
from stand.config import load_config
from stand.fake_mcp.sim import RobotSim
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.scenario import SCENARIOS_DIR, load_scenario
from stand.world.backend import MemoryWorld

sys.path.insert(0, str(Path(__file__).resolve().parent))

from robot_double import RobotDouble  # noqa: E402


def oc_mcp_server() -> Path:
    """Путь к bridge/server.py oc-mcp. Если его нет, тест пропускается."""
    path = load_config().oc_mcp_dir / "bridge" / "server.py"
    if not path.exists():
        pytest.skip(f"oc-mcp not found at {path.parent.parent}, set oc_mcp_dir")
    return path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_sim(sid: str = "s01-wall", pos=None, facing=None, inventory=None, setup=None) -> RobotSim:
    """RobotSim сценария (id или путь к yaml) с миром в памяти. Без аргументов робот стоит как в сценарии."""
    path = Path(sid) if sid.endswith(".yaml") else SCENARIOS_DIR / sid / "scenario.yaml"
    s = copy.deepcopy(load_scenario(path))
    if pos is not None:
        s.robot["pos"] = list(pos)
    if facing is not None:
        s.robot["facing"] = facing
    if inventory is not None:
        s.robot["inventory"] = inventory
    if setup:
        s.setup_blocks.update(setup)
    return RobotSim(s, Knowledge.load(KNOWLEDGE_DIR, s.knowledge), MemoryWorld(s.scene_blocks()))


@asynccontextmanager
async def bridge(sim: RobotSim, tmp_path: Path, **double_kwargs):
    """Запущенный мост oc-mcp (Upstream) и тестовый робот, который обслуживает его опрос."""
    port = free_port()
    cmd = bridge_cmd(oc_mcp_server(), sys.executable, port, tmp_path / "bridge.log", "stand")
    async with Upstream(cmd) as up:
        double = RobotDouble(sim, f"http://127.0.0.1:{port}", **double_kwargs)
        double.start()
        try:
            yield up
        finally:
            double.stop()
