"""Эталонные решения сценариев: у каждого сценария есть script.json, и он проходит.

Скрипт выполняется в процессе на fake-MCP с миром в памяти, затем мир оценивает судья.
Так ловится сценарий, который после правок fake-MCP или контракта стал нерешаемым.
Тот же прогон на живом сервере через runner: tests/stand/test_e2e_server.py.
"""

import json

import pytest

from stand.adapter_map import memory_snapshot
from stand.fake_mcp.action_log import ActionLog
from stand.fake_mcp.dispatch import Dispatcher
from stand.fake_mcp.sim import RobotSim
from stand.judge import judge
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.scenario import SCENARIOS_DIR, load_scenario
from stand.world.backend import MemoryWorld

SCENARIOS = sorted(p.name for p in SCENARIOS_DIR.iterdir() if (p / "scenario.yaml").exists())


@pytest.fixture(scope="module")
def k():
    return Knowledge.load(KNOWLEDGE_DIR)


@pytest.mark.parametrize("sid", SCENARIOS)
def test_scenario_script_passes(k, sid):
    s = load_scenario(SCENARIOS_DIR / sid / "scenario.yaml")
    calls = json.loads((SCENARIOS_DIR / sid / "script.json").read_text(encoding="utf-8"))
    world = MemoryWorld(s.scene_blocks())
    d = Dispatcher(RobotSim(s, k, world), "full", s.faults, ActionLog(None))
    for i, c in enumerate(calls, 1):
        env = d.call(c["tool"], c.get("args"))
        got = "ok" if env["ok"] else env["error_code"]
        assert got == c.get("expect", "ok"), (i, c, env)
    r = judge(memory_snapshot(world, s.region), s, k)
    assert r["passed"] and r["accuracy"] == 1.0 and r["extra_count"] == 0, r
