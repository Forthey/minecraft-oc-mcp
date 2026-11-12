"""Добавки контракта v2 поверх примитивов oc-mcp: move_to, face, place_at, get_status, verify_blocks."""

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


def _sim(k, sid="s01-wall", inventory=None, energy=1.0):
    s = copy.deepcopy(load_scenario(SCENARIOS_DIR / sid / "scenario.yaml"))
    s.robot["inventory"] = inventory if inventory is not None else [{"item": "minecraft:cobblestone", "count": 16}]
    s.robot["energy"] = energy
    world = MemoryWorld(s.scene_blocks())
    return RobotSim(s, Knowledge.load(KNOWLEDGE_DIR, s.knowledge), world), world


def test_place_at_sets_world_and_stands_next_to_target(k):
    sim, world = _sim(k)
    r = sim.place_at(100, 64, 100, "minecraft:cobblestone")
    assert r["ok"], r
    assert r["data"]["pos"] == [100, 64, 100] and r["data"]["slot"] == 1
    assert world.get((100, 64, 100)) == COBBLE and (100, 64, 100) in sim.placed
    assert sim.inventory.count("minecraft:cobblestone") == 15
    assert sum(abs(a - b) for a, b in zip(sim.pos, (100, 64, 100))) == 1


def test_place_at_accepts_short_and_full_id(k):
    sim, world = _sim(k)
    assert sim.place_at(100, 64, 100, "minecraft:cobblestone")["ok"]
    assert sim.place_at(101, 64, 100, "minecraft:cobblestone:0")["ok"]
    r = sim.verify_blocks([{"pos": [100, 64, 100], "item": "minecraft:cobblestone:0"},
                           {"pos": [101, 64, 100], "item": "minecraft:cobblestone"}])
    assert r["data"]["missing"] == [] and r["data"]["wrong"] == []


def test_face_then_place_front(k):
    sim, world = _sim(k)
    r = sim.face("east")
    assert r["ok"] and sim.facing == "east" and r["data"] == {"facing": "east"}
    assert sim.place("front", 1)["ok"]
    x, y, z = sim.pos
    assert world.get((x + 1, y, z)) == COBBLE
    assert sim.face("up")["error_code"] == "BLOCKED"


def test_place_at_occupied_and_floor(k):
    sim, _ = _sim(k)
    sim.place_at(100, 64, 100, "minecraft:cobblestone")
    assert sim.place_at(100, 64, 100, "minecraft:cobblestone")["error_code"] == "CANT_PLACE"
    assert sim.place_at(100, 63, 100, "minecraft:cobblestone")["error_code"] == "CANT_PLACE"


def test_place_at_enclosed_no_path(k):
    sim, _ = _sim(k, "s03-obstacle")
    assert sim.place_at(101, 65, 100, "minecraft:cobblestone")["error_code"] == "NO_PATH"


def test_place_at_from_side(k):
    sim, _ = _sim(k)
    assert sim.place_at(100, 64, 100, "minecraft:cobblestone", from_="up")["ok"]
    assert sim.pos == (100, 65, 100)
    assert sim.place_at(101, 64, 100, "minecraft:cobblestone", from_="down")["error_code"] == "NO_PATH"


def test_place_at_unknown_missing_and_not_block(k):
    sim, _ = _sim(k)
    assert sim.place_at(100, 64, 100, "nomod:thing")["error_code"] == "UNKNOWN_ITEM"
    assert sim.place_at(100, 64, 100, "minecraft:planks")["error_code"] == "NO_ITEM"
    sim2, _ = _sim(k, inventory=[{"item": "minecraft:stick", "count": 2}])
    assert sim2.place_at(100, 64, 100, "minecraft:stick")["error_code"] == "CANT_PLACE"


def test_move_to_outside_region(k):
    sim, _ = _sim(k)
    assert sim.move_to(200, 64, 100)["error_code"] == "OUT_OF_RANGE"
    assert sim.place_at(200, 64, 100, "minecraft:cobblestone")["error_code"] == "OUT_OF_RANGE"


def test_move_to_avoid_steps(k):
    sim, _ = _sim(k)
    r = sim.move_to(100, 64, 102)
    assert r["ok"] and r["data"]["pos"] == [100, 64, 102] and r["data"]["steps"] == 3
    assert sim.pos == (100, 64, 102)


def test_move_to_occupied_target_and_dig_through(k):
    sim, world = _sim(k, "s03-obstacle")
    target = next(p for p, b in sim.occ.items() if p[1] == 64 and b[0] == "minecraft:stone")
    assert sim.move_to(*target)["error_code"] == "BLOCKED"
    r = sim.move_to(*target, policy="dig_through")
    assert r["ok"] and list(target) in r["data"]["dug"]
    assert world.get(target) == ("minecraft:air", 0)


def test_get_status_shape(k):
    sim, _ = _sim(k)
    r = sim.get_status()
    assert r["ok"]
    assert set(r["data"]) == {"pos", "facing", "inventory"}
    assert r["data"]["inventory"] == [{"slot": 1, "count": 16, "name": "minecraft:cobblestone:0"}]


def test_verify_blocks_missing_wrong_pages(k):
    sim, _ = _sim(k)
    sim.place_at(100, 64, 100, "minecraft:cobblestone")
    r = sim.verify_blocks([{"pos": [100, 64, 100], "item": "minecraft:planks"},
                           {"pos": [101, 64, 100], "item": "minecraft:cobblestone"}])
    assert r["data"]["wrong"] == [{"pos": [100, 64, 100], "item": "minecraft:planks:0"}]
    assert r["data"]["missing"] == [{"pos": [101, 64, 100], "item": "minecraft:cobblestone:0"}]
    many = [{"pos": [100, 64, 100], "item": "minecraft:cobblestone"}] * 60
    first = sim.verify_blocks(many)
    assert first["data"]["checked"] == 50 and first["data"]["next_page"] == 1
    assert sim.verify_blocks(many, page=1)["data"]["next_page"] is None


def test_search_docs(k):
    sim, _ = _sim(k)
    r = sim.search_docs("reactor")
    assert r["ok"] and r["data"]["docs"]
