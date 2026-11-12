from __future__ import annotations

import anyio
import pytest
from adapter_harness import bridge, make_sim

from adapter.action_log import ActionLog
from adapter.explored_map import ExploredMap
from adapter.robot import RobotAdapter

STONE = ("minecraft:stone", 0)
WALL = {(x, y, 102): STONE for x in range(97, 104) for y in (64, 65)}


def _run(sim, tmp_path, worldmap, script, link=None):
    async def go():
        async with bridge(sim, tmp_path) as up:
            ad = RobotAdapter(up, worldmap, ActionLog(None), link=link)
            await ad.start()
            return await script(ad)

    return anyio.run(go)



def test_geo_scan_then_move_to_avoids_wall(tmp_path):
    sim = make_sim(setup=WALL)
    m = ExploredMap("w", tmp_path / "explore.db")

    async def script(ad):
        scan = await ad.call("geo_scan", {"x": -4, "z": 0, "y": 0, "width": 8, "depth": 4, "height": 2})
        assert scan["ok"], scan
        return await ad.call("move_to", {"x": 100, "y": 64, "z": 99})

    env = _run(sim, tmp_path, m, script)
    assert env["ok"], env
    assert sim.pos == (100, 64, 99)
    assert m.occupied((100, 64, 102))
    assert env["data"]["dug"] == []
    assert ExploredMap("w", tmp_path / "explore.db").occupied((100, 65, 102))


def test_blocked_move_marks_cell_and_replans(tmp_path):
    sim = make_sim(setup=WALL)
    m = ExploredMap("w")

    async def script(ad):
        return await ad.call("move_to", {"x": 100, "y": 64, "z": 99})

    env = _run(sim, tmp_path, m, script)
    assert env["ok"], env
    assert sim.pos == (100, 64, 99)
    assert m.occupied((100, 64, 102))


def test_memory_hazard_blocks_path(tmp_path):
    pytest.importorskip("memory_mcp")
    from memory_mcp.schemas import PoiRecord

    from adapter.memory_link import MemoryLink

    link = MemoryLink("w", robot_id="r", db_path=tmp_path / "memory.db")
    link.repo.remember_poi(link._ctx(), PoiRecord(kind="hazard", label="lava", dim=0, x=100, y=64, z=102, radius=1))
    link._loaded_at = 0.0
    sim = make_sim()
    m = ExploredMap("w", hazards=link)

    async def script(ad):
        return await ad.call("move_to", {"x": 100, "y": 64, "z": 99})

    try:
        env = _run(sim, tmp_path, m, script, link)
    finally:
        link.close()
    assert env["ok"], env
    assert sim.pos == (100, 64, 99)
    assert env["data"]["steps"] > 6


def test_verify_reports_unverified(tmp_path):
    sim = make_sim(setup=WALL)
    m = ExploredMap("w")

    async def script(ad):
        await ad.call("geo_scan", {"x": -4, "z": 0, "y": 0, "width": 8, "depth": 4, "height": 2})
        return await ad.call("verify_blocks", {"expected": [
            {"pos": [100, 64, 102], "item": "minecraft:stone"},
            {"pos": [100, 64, 104], "item": "minecraft:stone"},
        ]})

    env = _run(sim, tmp_path, m, script)
    assert env["ok"], env
    assert env["data"]["unverified"] == [{"pos": [100, 64, 102], "item": "minecraft:stone:0"}]
    assert env["data"]["missing"] == [{"pos": [100, 64, 104], "item": "minecraft:stone:0"}]
