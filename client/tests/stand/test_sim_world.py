"""Модель робота v2: движение, установка и разрушение блоков, зрение."""

import copy
import json

import pytest

from stand.fake_mcp.inventory import Inventory
from stand.fake_mcp.sim import RobotSim
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.scenario import SCENARIOS_DIR, load_scenario
from stand.world.backend import MemoryWorld

COBBLE = ("minecraft:cobblestone", 0)
STONE = ("minecraft:stone", 0)


@pytest.fixture(scope="module")
def k():
    return Knowledge.load(KNOWLEDGE_DIR)


def _sim(k, inventory=None, energy=1.0, setup=None, pos=(100, 64, 105), facing="north"):
    s = copy.deepcopy(load_scenario(SCENARIOS_DIR / "s01-wall" / "scenario.yaml"))
    s.robot["inventory"] = inventory if inventory is not None else [{"item": "minecraft:cobblestone", "count": 9}]
    s.robot["energy"] = energy
    s.robot["pos"] = list(pos)
    s.robot["facing"] = facing
    if setup:
        s.setup_blocks.update(setup)
    world = MemoryWorld(s.scene_blocks())
    return RobotSim(s, k, world), world


def test_inventory_slot_helpers():
    inv = Inventory()
    inv.set_slot(3, "minecraft:stick", 5)
    assert inv.slot(3) == ("minecraft:stick", 5)
    assert inv.slot(1) is None
    assert inv.first_slot_with("minecraft:stick") == 3
    assert inv.first_slot_with("minecraft:planks") is None
    inv.set_slot(3, None, 0)
    assert inv.slot(3) is None


def test_move_forward_and_blocked(k):
    sim, _ = _sim(k, setup={(100, 64, 102): STONE})
    r = sim.move("forward", 3)
    assert r["ok"] is False and r["error_code"] == "BLOCKED"
    assert r["message"] == "moved 2 of 3 blocks forward, blocked: solid"
    assert sim.pos == (100, 64, 103)
    ok = sim.move("up", 2)
    assert ok["ok"] and ok["message"] == "Moved up 2 blocks." and sim.pos == (100, 66, 103)


def test_move_region_edge_is_solid(k):
    sim, _ = _sim(k, pos=(100, 64, 110), facing="south")
    r = sim.move("forward", 1)
    assert r["error_code"] == "BLOCKED" and r["message"] == "moved 0 of 1 blocks forward, blocked: solid"


def test_turn_changes_front(k):
    sim, _ = _sim(k)
    r = sim.turn("right")
    assert r["ok"] and r["message"] == "Turned right." and sim.facing == "east"
    assert sim.side_pos("front") == (101, 64, 105)
    sim.turn("around")
    assert sim.facing == "west"
    sim.turn("left")
    assert sim.facing == "south"


def test_place_from_slot_sets_world_and_placed(k):
    sim, world = _sim(k)
    r = sim.place("front", 1)
    assert r["ok"], r
    assert r["message"] == "Placed from slot 1 front: minecraft:cobblestone. 8 left in slot 1."
    assert r["data"]["pos"] == [100, 64, 104]
    assert world.get((100, 64, 104)) == COBBLE and sim.occ[(100, 64, 104)] == COBBLE
    assert (100, 64, 104) in sim.placed
    assert sim.inventory.slot(1) == ("minecraft:cobblestone", 8)


def test_place_uses_selected_slot_by_default(k):
    sim, _ = _sim(k)
    r = sim.place("down")
    assert r["error_code"] == "BLOCKED"  # под роботом пол
    assert "down is occupied by minecraft:grass" in r["message"]


def test_place_empty_slot_and_occupied(k):
    sim, _ = _sim(k, setup={(100, 64, 104): STONE})
    empty = sim.place("front", 2)
    assert empty["error_code"] == "NO_ITEM" and empty["message"] == "slot 2 is empty, nothing to place"
    busy = sim.place("front", 1)
    assert busy["error_code"] == "BLOCKED"
    assert busy["message"] == ("cannot place from slot 1 front: block in the way; front is occupied by "
                               "minecraft:stone (break it with swing first)")


def test_place_non_block_item(k):
    sim, _ = _sim(k, inventory=[{"item": "minecraft:stick", "count": 2}])
    r = sim.place("front", 1)
    assert r["error_code"] == "CANT_PLACE" and r["message"] == "cannot place from slot 1 front: item is not a block"


def test_swing_breaks_and_collects(k):
    sim, world = _sim(k, inventory=[], setup={(100, 64, 104): STONE})
    r = sim.swing("front")
    assert r["ok"], r
    assert r["message"] == ("Broke minecraft:stone (front); drops went to the inventory. no tool equipped.")
    assert r["data"] == {"pos": [100, 64, 104], "block": "minecraft:stone"}
    assert world.get((100, 64, 104)) == ("minecraft:air", 0)
    assert sim.inventory.count("minecraft:stone") == 1


def test_swing_air(k):
    sim, _ = _sim(k)
    r = sim.swing("front")
    assert r["error_code"] == "BLOCKED" and r["message"] == "nothing to hit on front (air)"


def test_swing_bedrock_tool_broken(k):
    sim, _ = _sim(k, setup={(100, 64, 104): ("minecraft:bedrock", 0)})
    r = sim.swing("front")
    assert r["error_code"] == "TOOL_BROKEN"
    assert r["message"].startswith("cannot break minecraft:bedrock (front) with the equipped tool (no tool equipped).")


def test_use_has_no_effect(k):
    sim, _ = _sim(k)
    r = sim.use("front")
    assert r["ok"] and r["message"] == "Used front: nothing."


def test_surroundings_relative_to_facing(k):
    sim, _ = _sim(k, facing="east", setup={(101, 64, 105): STONE, (100, 64, 104): COBBLE})
    r = sim.surroundings()
    assert r["ok"]
    sides = r["data"]["sides"]
    assert sides["front"] == {"block": "minecraft:stone", "kind": "solid"}
    assert sides["left"] == {"block": "minecraft:cobblestone", "kind": "solid"}
    assert sides["right"] == {"block": "minecraft:air", "kind": "air"}
    assert sides["down"]["kind"] == "solid"
    assert "front: minecraft:stone (solid)" in r["message"].splitlines()


def test_geo_scan_volume_limit_and_values(k):
    sim, _ = _sim(k, setup={(100, 64, 104): STONE})
    too_big = sim.geo_scan(width=8, depth=8, height=2)
    assert too_big["error_code"] == "BLOCKED" and too_big["message"] == "width*depth*height must be <= 64"
    r = sim.geo_scan(x=0, z=1, y=-1, width=1, depth=1, height=2)
    assert r["ok"]
    # Ось z робота смотрит вперёд (north): z=1 это клетка (100, *, 104). y=-1 пол, y=0 камень.
    assert r["data"]["hardness"] == [[[1.5]], [[1.5]]]


def test_world_info_shape(k):
    sim, _ = _sim(k)
    r = sim.world_info()
    assert r["ok"]
    assert r["data"] == {"robot_id": "fake-robot", "robot_name": "robot", "x": 100, "y": 64, "z": 105,
                         "facing": "north", "world_id": "stand"}
    assert json.loads(r["message"]) == r["data"]


def test_no_energy(k):
    sim, _ = _sim(k, energy=0.0)
    r = sim.move("forward", 1)
    assert r["error_code"] == "NO_ENERGY" and r["message"] == "not enough energy"
