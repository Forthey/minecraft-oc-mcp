from __future__ import annotations

import anyio
from adapter_harness import bridge, make_sim

from adapter.action_log import ActionLog
from adapter.explored_map import ExploredMap
from adapter.robot import RobotAdapter

STONE = ("minecraft:stone", 0)
WALL = {(x, y, 102): STONE for x in range(97, 104) for y in (64, 65)}


def _run(sim, tmp_path, worldmap, script):
    async def go():
        async with bridge(sim, tmp_path) as up:
            ad = RobotAdapter(up, worldmap, ActionLog(None))
            await ad.start()
            return await script(ad)

    return anyio.run(go)


def test_scan_area_splits_box_and_fills_map(tmp_path):
    sim = make_sim(setup=WALL)
    m = ExploredMap("w")

    async def script(ad):
        return await ad.call("scan_area", {"x1": 95, "y1": 64, "z1": 100, "x2": 106, "y2": 65, "z2": 104})

    env = _run(sim, tmp_path, m, script)
    assert env["ok"], env
    solid = {tuple(c[:3]) for c in env["data"]["solid"]}
    assert set(WALL) <= solid
    assert env["data"]["scanned"] == 12 * 2 * 5
    assert env["data"]["skipped"] == [] and env["data"]["failed"] == 0
    assert all(m.occupied(p) for p in WALL)


def test_scan_area_skips_far_chunks(tmp_path):
    sim = make_sim()

    async def script(ad):
        return await ad.call("scan_area", {"x1": 98, "y1": 64, "z1": 100, "x2": 160, "y2": 64, "z2": 100})

    env = _run(sim, tmp_path, ExploredMap("w"), script)
    assert env["ok"], env
    assert env["data"]["skipped"]
    assert "out of geolyzer range" in env["message"]


def test_scan_area_too_big_is_blocked(tmp_path):
    sim = make_sim()

    async def script(ad):
        return await ad.call("scan_area", {"x1": 0, "y1": 0, "z1": 0, "x2": 63, "y2": 1, "z2": 63})

    env = _run(sim, tmp_path, ExploredMap("w"), script)
    assert not env["ok"] and env["error_code"] == "BLOCKED"
