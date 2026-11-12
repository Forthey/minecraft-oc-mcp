import os
import stat
import sys

import anyio
from adapter_harness import bridge, make_sim

from adapter.action_log import ActionLog
from adapter.java_pathfinding import JavaPathfinder, densify, parse_cells
from adapter.robot import RobotAdapter
from adapter.worldmap import NoMap
from stand.adapter_map import SnapshotMap, memory_snapshot

STONE = ("minecraft:stone", 0)


class FakePathfinder:
    def __init__(self, route, long_range=3):
        self._route = route
        self.long_range = long_range
        self.calls = []

    async def route(self, start, goal, facing):
        self.calls.append((start, goal, facing))
        return self._route


def _run(sim, tmp_path, pf, script, with_map=False):
    async def go():
        async with bridge(sim, tmp_path) as up:
            world_map = SnapshotMap(sim.region, sim.k, lambda: memory_snapshot(sim.world, sim.region), sim.world) \
                if with_map else NoMap()
            ad = RobotAdapter(up, world_map, ActionLog(None), pf)
            await ad.start()
            return await script(ad)

    return anyio.run(go)


def test_parse_and_densify():
    assert parse_cells("log\n[[1,2,3],[1,2,5]]") == [(1, 2, 3), (1, 2, 5)]
    assert parse_cells("Forward 3") is None
    assert densify([(0, 0, 0), (2, 1, 0)]) == [(0, 0, 0), (0, 1, 0), (1, 1, 0), (2, 1, 0)]


def test_long_move_to_follows_route_without_map(tmp_path):
    sim = make_sim()
    pf = FakePathfinder([(100, 64, 105), (100, 65, 105), (100, 65, 100), (104, 65, 100)])

    async def script(ad):
        return await ad.call("move_to", {"x": 104, "y": 65, "z": 100})

    env = _run(sim, tmp_path, pf, script)
    assert env["ok"], env
    assert sim.pos == (104, 65, 100)
    assert env["data"]["steps"] == 1 + 5 + 4
    assert pf.calls == [((100, 64, 105), (104, 65, 100), "north")]


def test_short_move_to_skips_pathfinder(tmp_path):
    sim = make_sim()
    pf = FakePathfinder(None, long_range=32)

    async def script(ad):
        return await ad.call("move_to", {"x": 100, "y": 64, "z": 102})

    env = _run(sim, tmp_path, pf, script, with_map=True)
    assert env["ok"], env
    assert pf.calls == []


def test_long_move_to_blocked_without_map(tmp_path):
    sim = make_sim()
    pf = FakePathfinder([(100, 64, 105), (100, 64, 100)])

    async def script(ad):
        sim.occ[(100, 64, 102)] = STONE
        return await ad.call("move_to", {"x": 100, "y": 64, "z": 100})

    env = _run(sim, tmp_path, pf, script)
    assert env["error_code"] == "BLOCKED"
    assert env["data"]["pos"] == [100, 64, 103] and env["data"]["steps"] == 2


def test_long_move_to_falls_back_to_map(tmp_path):
    sim = make_sim()
    pf = FakePathfinder([(100, 64, 105), (100, 64, 100)])

    async def script(ad):
        sim.occ[(100, 64, 102)] = STONE
        sim.world.set_block((100, 64, 102), STONE)
        return await ad.call("move_to", {"x": 100, "y": 64, "z": 100})

    env = _run(sim, tmp_path, pf, script, with_map=True)
    assert env["ok"], env
    assert sim.pos == (100, 64, 100)


def test_long_move_to_no_route(tmp_path):
    sim = make_sim()

    async def script(ad):
        return await ad.call("move_to", {"x": 100, "y": 64, "z": 100})

    env = _run(sim, tmp_path, FakePathfinder(None), script)
    assert env["error_code"] == "NO_PATH"


def test_java_pathfinder_runs_process(tmp_path):
    fake = tmp_path / "fake_java"
    fake.write_text(f"#!{sys.executable}\nimport sys, json\nprint('noise')\n"
                    "a = sys.argv[1:]\nassert a[0] == '-jar' and a[2] == '--cells'\n"
                    "print(json.dumps([[int(a[4]), int(a[5]), int(a[6])], [int(a[7]), int(a[8]), int(a[9])]]))\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    pf = JavaPathfinder("pf.jar", tmp_path, java=str(fake))
    assert anyio.run(pf.route, (1, 2, 3), (4, 5, 6), "east") == [(1, 2, 3), (4, 5, 6)]
    broken = JavaPathfinder("pf.jar", tmp_path, java=os.devnull)
    assert anyio.run(broken.route, (1, 2, 3), (4, 5, 6), "east") is None
