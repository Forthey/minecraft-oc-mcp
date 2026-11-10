import copy

import pytest

from stand.fake_mcp.sim import RobotSim
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.scenario import SCENARIOS_DIR, load_scenario
from stand.world.backend import MemoryWorld

COBBLE = ("minecraft:cobblestone", 0)


@pytest.fixture(scope="module")
def k():
    return Knowledge.load(KNOWLEDGE_DIR)


def _sim(k, sid="s01-wall", inventory=None, energy=1.0, setup=None, robot_pos=None):
    s = copy.deepcopy(load_scenario(SCENARIOS_DIR / sid / "scenario.yaml"))
    s.robot["inventory"] = inventory if inventory is not None else [{"item": "minecraft:cobblestone", "count": 16}]
    s.robot["energy"] = energy
    if robot_pos:
        s.robot["pos"] = robot_pos
    if setup:
        s.setup_blocks.update(setup)
    world = MemoryWorld(s.scene_blocks())
    return RobotSim(s, k, world), world


def test_place_at_sets_world_and_occ(k):
    sim, world = _sim(k)
    r = sim.place_at(100, 64, 100, "minecraft:cobblestone")
    assert r["ok"], r
    assert world.get((100, 64, 100)) == COBBLE
    assert sim.occ[(100, 64, 100)] == COBBLE
    assert sim.inventory.count("minecraft:cobblestone") == 15
    # Робот стоит рядом с целью.
    assert sum(abs(a - b) for a, b in zip(sim.pos, (100, 64, 100))) == 1
    assert (100, 64, 100) in sim.placed


def test_place_at_occupied_cant_place(k):
    sim, _ = _sim(k)
    sim.place_at(100, 64, 100, "minecraft:cobblestone")
    r = sim.place_at(100, 64, 100, "minecraft:cobblestone")
    assert r == {**r, "ok": False, "error_code": "CANT_PLACE"}


def test_place_at_floor_cant_place(k):
    sim, _ = _sim(k)
    assert sim.place_at(100, 63, 100, "minecraft:cobblestone")["error_code"] == "CANT_PLACE"


def test_place_at_enclosed_no_path(k):
    sim, _ = _sim(k, "s03-obstacle")
    r = sim.place_at(101, 65, 100, "minecraft:cobblestone")
    assert r["error_code"] == "NO_PATH"


def test_place_at_from_side(k):
    sim, _ = _sim(k)
    r = sim.place_at(100, 64, 100, "minecraft:cobblestone", from_="up")
    assert r["ok"], r
    assert sim.pos == (100, 65, 100)
    assert sim.place_at(101, 64, 100, "minecraft:cobblestone", from_="down")["error_code"] == "NO_PATH"


def test_place_at_unknown_and_missing_item(k):
    sim, _ = _sim(k)
    assert sim.place_at(100, 64, 100, "nomod:thing")["error_code"] == "UNKNOWN_ITEM"
    assert sim.place_at(100, 64, 100, "minecraft:planks")["error_code"] == "NO_ITEM"
    sim2, _ = _sim(k, inventory=[{"item": "minecraft:stick", "count": 2}])
    assert sim2.place_at(100, 64, 100, "minecraft:stick")["error_code"] == "CANT_PLACE"


def test_move_to_outside_region(k):
    sim, _ = _sim(k)
    assert sim.move_to(200, 64, 100)["error_code"] == "OUT_OF_RANGE"
    assert sim.place_at(200, 64, 100, "minecraft:cobblestone")["error_code"] == "OUT_OF_RANGE"


def test_move_to_avoid_and_steps(k):
    sim, _ = _sim(k)
    r = sim.move_to(100, 64, 101)
    assert r["ok"] and r["data"]["pos"] == [100, 64, 101] and r["data"]["steps"] == 4
    assert sim.energy == pytest.approx(1.0 - 4 * 0.0005)


def test_move_to_occupied_target_avoid_blocked(k):
    sim, _ = _sim(k, setup={(100, 64, 101): ("minecraft:stone", 0)})
    assert sim.move_to(100, 64, 101)["error_code"] == "BLOCKED"


def test_dig_through_breaks_and_collects(k):
    sim, world = _sim(k, "s03-obstacle", inventory=[])
    assert sim.move_to(101, 65, 100, "avoid")["error_code"] == "NO_PATH"
    r = sim.move_to(101, 65, 100, "dig_through")
    assert r["ok"], r
    dug = [tuple(p) for p in r["data"]["dug"]]
    assert len(dug) >= 1
    for p in dug:
        assert world.get(p) == ("minecraft:air", 0)
        assert p not in sim.occ
    assert sim.inventory.count("minecraft:stone") == len(dug)


def test_dig_side(k):
    sim, world = _sim(k, setup={(100, 64, 104): ("minecraft:stone", 0)}, inventory=[])
    r = sim.dig("front")
    assert r["ok"], r
    assert world.get((100, 64, 104)) == ("minecraft:air", 0)
    assert sim.inventory.count("minecraft:stone") == 1
    assert sim.dig("front")["error_code"] == "BLOCKED"
    assert sim.dig("down")["ok"]
    assert sim.inventory.count("minecraft:grass") == 1


def test_no_energy(k):
    sim, _ = _sim(k, energy=0.0)
    assert sim.move_to(100, 64, 101)["error_code"] == "NO_ENERGY"
    assert sim.place_at(100, 64, 100, "minecraft:cobblestone")["error_code"] == "NO_ENERGY"
    assert sim.pos == (100, 64, 105)


def test_inspect_relative_sides(k):
    sim, _ = _sim(k, setup={(100, 64, 104): ("minecraft:stone", 0), (101, 64, 105): ("minecraft:planks", 1)})
    assert sim.inspect("front")["data"]["item"] == "minecraft:stone"
    assert sim.inspect("right")["data"]["item"] == "minecraft:planks:1"
    assert sim.inspect("down")["data"]["item"] == "minecraft:grass"
    assert sim.inspect("up")["data"]["item"] == "minecraft:air"
    assert sim.face("east")["ok"]
    # Робот смотрит на восток: слева север, то есть (100, 64, 104).
    assert sim.inspect("left")["data"]["item"] == "minecraft:stone"


def test_move_low_level(k):
    sim, _ = _sim(k, setup={(100, 64, 102): ("minecraft:stone", 0)})
    r = sim.move("forward", 5)
    assert r["error_code"] == "BLOCKED"
    assert r["data"]["moved"] == 2 and sim.pos == (100, 64, 103)
    assert sim.move("up", 1)["ok"] and sim.pos == (100, 65, 103)


def test_scan_area_summary_and_full(k):
    sim, _ = _sim(k)
    sim.place_at(100, 64, 100, "minecraft:cobblestone")
    box = {"from": [99, 64, 99], "to": [101, 64, 101]}
    s = sim.scan_area(box)["data"]
    assert s["cells"] == 9 and s["solid"] == 1 and s["air"] == 8
    assert s["blocks"] == {"minecraft:cobblestone": 1}
    full = sim.scan_area(box, "full")["data"]
    assert full["blocks"] == [{"pos": [100, 64, 100], "item": "minecraft:cobblestone"}]
    assert sim.scan_area({"from": [0, 64, 0], "to": [1, 64, 1]})["error_code"] == "OUT_OF_RANGE"


def test_get_status_shape(k):
    sim, _ = _sim(k)
    d = sim.get_status()["data"]
    assert set(d) == {"pos", "facing", "energy", "tool", "inventory", "warehouse"}
    assert d["pos"] == [100, 64, 105] and d["facing"] == "north"
    assert d["inventory"]["used"] == 1 and d["inventory"]["total"] == 16
    assert d["warehouse"] == {"pos": [95, 64, 105], "side": "east"}
