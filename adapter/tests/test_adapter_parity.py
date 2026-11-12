"""Паритет fake-MCP и адаптера: на одних и тех же вызовах агент видит одинаковые конверты.

Агентов оценивают на fake-MCP, а работать им с адаптером над oc-mcp. Если fake отдаёт
в data поля, которых нет у адаптера, агент к ним привыкнет и сломается на настоящем роботе.
Адаптер здесь стоит на тестовом роботе с тем же RobotSim, поэтому сравнивается именно
слой конверта: коды ошибок, message и data.
"""

import copy
import json
import re

import anyio
import pytest
from adapter_harness import bridge, make_sim

from adapter.action_log import ActionLog
from adapter.robot import RobotAdapter
from stand.adapter_map import SnapshotMap, memory_snapshot
from stand.fake_mcp.action_log import ActionLog as FakeLog
from stand.fake_mcp.dispatch import TOOL_SPECS, Dispatcher
from stand.scenario import SCENARIOS_DIR

SCRIPTED = sorted(p.parent.name for p in SCENARIOS_DIR.glob("*/script.json"))

# Обход всех сквозных tools на сцене s02: брёвна на складе, крафт досок, мелкие действия.
TOUR = [
    {"tool": "world_info", "args": {}},
    {"tool": "move_to", "args": {"x": 96, "y": 64, "z": 105}},
    {"tool": "face", "args": {"direction": "west"}},
    {"tool": "storage_scan", "args": {"side": "front"}},
    {"tool": "storage_take", "args": {"side": "front", "slot": 1, "count": 2}},
    {"tool": "nei_find", "args": {"text": "oak", "limit": 3}},
    {"tool": "nei_recipes", "args": {"item": "minecraft:planks:0"}},
    {"tool": "nei_recipe", "args": {"recipe": "r0480444c7f792b19"}},
    {"tool": "nei_craft_tree", "args": {"item": "minecraft:planks:0", "count": 8, "use_inventory": True}},
    {"tool": "craft_recipe", "args": {"recipe": "r0480444c7f792b19", "count": 2}},
    {"tool": "inventory_scan", "args": {}},
    {"tool": "inventory_transfer", "args": {"from_slot": 4, "to_slot": 2, "count": 3}},
    {"tool": "storage_put", "args": {"side": "front", "robot_slot": 2, "count": 1}},
    {"tool": "nei_machine_plan", "args": {"side": "front", "recipe": "r0480444c7f792b19"}},
    {"tool": "craft", "args": {"count": 1}},
    {"tool": "equip", "args": {"slot": 2}},
    {"tool": "surroundings", "args": {}},
    {"tool": "geo_scan", "args": {"x": -1, "z": 0, "y": 0, "width": 3, "depth": 2, "height": 1}},
    {"tool": "scan_area", "args": {"x1": 90, "y1": 63, "z1": 100, "x2": 101, "y2": 66, "z2": 109}},
    {"tool": "scan_area", "args": {"x1": 90, "y1": 63, "z1": 100, "x2": 140, "y2": 64, "z2": 101}},
    {"tool": "turn", "args": {"direction": "around"}},
    {"tool": "move", "args": {"direction": "forward", "n": 2}},
    {"tool": "move", "args": {"direction": "up", "n": 1}},
    {"tool": "place", "args": {"side": "down", "slot": 4}},
    {"tool": "swing", "args": {"side": "down"}},
    {"tool": "use", "args": {"side": "front"}},
    {"tool": "move", "args": {"direction": "forward", "n": 30}},
    {"tool": "place_at", "args": {"x": 100, "y": 64, "z": 100, "item": "minecraft:planks"}},
    {"tool": "move_to", "args": {"x": 500, "y": 64, "z": 100}},
    {"tool": "get_status", "args": {}},
    {"tool": "verify_blocks", "args": {"expected": [{"pos": [100, 64, 100], "item": "minecraft:planks"}]}},
    {"tool": "get_action_log", "args": {"last_n": 3}},
]

DAMAGE = re.compile(r"^([^:]+:[^:]+):\d+$")


def _strip_damage(value):
    """Имена предметов без damage: oc-mcp его пока не печатает (TODO в docs/real-mcp-notes.md)."""
    if isinstance(value, dict):
        return {k: _strip_damage(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_damage(v) for v in value]
    if isinstance(value, str) and (m := DAMAGE.match(value)):
        return m.group(1)
    return value


def _fake(sid: str, calls: list[dict]) -> list[dict]:
    d = Dispatcher(make_sim(sid), "full", [], FakeLog(None))
    return [d.call(c["tool"], c["args"]) for c in calls]


def _adapter(sid: str, calls: list[dict], tmp_path) -> list[dict]:
    sim = make_sim(sid)

    async def go():
        async with bridge(sim, tmp_path) as up:
            world_map = SnapshotMap(sim.region, sim.k, lambda: memory_snapshot(sim.world, sim.region), sim.world)
            ad = RobotAdapter(up, world_map, ActionLog(None))
            await ad.start()
            return [await ad.call(c["tool"], c["args"]) for c in calls]

    return anyio.run(go)


def _assert_same(calls, fake, real):
    for i, (c, f, r) in enumerate(zip(calls, fake, real, strict=True), 1):
        assert _strip_damage(copy.deepcopy(r)) == _strip_damage(copy.deepcopy(f)), \
            f"call {i} {c['tool']}\nfake    {json.dumps(f)[:400]}\nadapter {json.dumps(r)[:400]}"


@pytest.mark.parametrize("sid", SCRIPTED)
def test_scenario_script_parity(tmp_path, sid):
    calls = json.loads((SCENARIOS_DIR / sid / "script.json").read_text(encoding="utf-8"))
    _assert_same(calls, _fake(sid, calls), _adapter(sid, calls, tmp_path))


def test_every_tool_parity(tmp_path):
    names = {c["tool"] for c in TOUR}
    # search_docs не сравнивается: у адаптера нет сервиса документации, он всегда UNSUPPORTED.
    assert names | {"search_docs"} == set(TOOL_SPECS)
    _assert_same(TOUR, _fake("s02-craft", TOUR), _adapter("s02-craft", TOUR, tmp_path))
