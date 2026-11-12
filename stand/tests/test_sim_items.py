"""Модель робота v2: инвентарь, хранилища, крафт и NEI."""

import copy
import json

import pytest

from stand.fake_mcp.inventory import Container, Inventory
from stand.fake_mcp.nei import CRAFT_GRID
from stand.fake_mcp.sim import RobotSim
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.scenario import SCENARIOS_DIR, load_scenario
from stand.world.backend import MemoryWorld

NEXT_TO_WAREHOUSE = (96, 64, 105)  # склад s01 в (95, 64, 105), робот смотрит на west


@pytest.fixture(scope="module")
def k():
    return Knowledge.load(KNOWLEDGE_DIR)


def _sim(k, inventory=None, warehouse=None, at_warehouse=True):
    s = copy.deepcopy(load_scenario(SCENARIOS_DIR / "s01-wall" / "scenario.yaml"))
    s.robot["inventory"] = inventory if inventory is not None else []
    if warehouse is not None:
        s.warehouse["items"] = warehouse
    if at_warehouse:
        s.robot["pos"] = list(NEXT_TO_WAREHOUSE)
        s.robot["facing"] = "west"
    world = MemoryWorld(s.scene_blocks())
    return RobotSim(s, k, world)


def _total(sim) -> int:
    return sum(n for _, n in (sim.inventory.slot(i) or ("", 0) for i in range(1, 17)))


def _recipe(sim, item):
    return sim.nei_recipes(item)["data"]["results"][0]["recipes"][0]["id"]


def test_inventory_add_remove_stacks():
    inv = Inventory(slots=2, stack=64)
    assert inv.add("a", 100) == 0
    assert inv.add("a", 40) == 12
    assert inv.count("a") == 128
    assert not inv.remove("a", 200) and inv.count("a") == 128
    assert inv.remove("a", 70) and inv.count("a") == 58


def test_container_slots():
    c = Container(3)
    assert c.put_slot(0, "a", 70) == 6
    assert c.take_slot(0, "a", 10) == 10 and c.slot_count(0, "a") == 54


def test_storage_take_slot_one_is_first_chest_slot(k):
    sim = _sim(k)
    r = sim.storage_take("front", 1, 9)
    assert r["ok"], r
    assert r["message"] == "Took items from front slot 1."
    assert sim.inventory.slot(1) == ("minecraft:cobblestone", 9)
    assert sim.containers[(95, 64, 105)].count("minecraft:cobblestone") == 23


def test_storage_take_whole_slot_by_default(k):
    sim = _sim(k)
    assert sim.storage_take("front", 1)["ok"]
    assert sim.inventory.count("minecraft:cobblestone") == 32


def test_storage_take_empty_full_and_no_container(k):
    sim = _sim(k)
    r = sim.storage_take("front", 5, 1)
    assert r["error_code"] == "NO_ITEM" and r["message"] == "cannot take items from front slot 5: slot is empty"
    full = _sim(k, inventory=[{"item": "minecraft:stick", "count": 64 * 16}])
    r = full.storage_take("front", 1, 1)
    assert r["error_code"] == "INVENTORY_FULL"
    assert r["message"] == "cannot take items from front slot 1: robot inventory is full"
    away = _sim(k, at_warehouse=False)
    r = away.storage_take("front", 1, 1)
    assert r["error_code"] == "BLOCKED" and r["message"] == "cannot take items from front slot 1: no inventory"


def test_storage_put_back(k):
    sim = _sim(k, inventory=[{"item": "minecraft:stick", "count": 3}])
    r = sim.storage_put("front", 1, 2, 10)
    assert r["ok"] and r["message"] == "Put items from robot slot 1 front."
    assert sim.containers[(95, 64, 105)].slot_count(9, "minecraft:stick") == 2
    assert sim.inventory.slot(1) == ("minecraft:stick", 1)


def test_storage_scan_lines_and_data(k):
    sim = _sim(k)
    r = sim.storage_scan("front")
    assert r["ok"]
    assert r["message"].splitlines()[:3] == [
        "Block: minecraft:chest", "Storage has 27 slots.", "slot 1: 32x minecraft:cobblestone:0 (Cobblestone)",
    ]
    assert r["data"]["slots"] == [{"slot": 1, "count": 32, "name": "minecraft:cobblestone:0", "label": "Cobblestone"}]
    assert r["data"]["size"] == 27 and r["data"]["block"] == "minecraft:chest"


def test_inventory_scan_lines_and_empty(k):
    assert _sim(k).inventory_scan()["message"] == "Robot inventory is empty."
    sim = _sim(k, inventory=[{"item": "minecraft:planks:1", "count": 4}])
    r = sim.inventory_scan()
    label = k.items["minecraft:planks:1"]["name"]
    assert r["message"] == f"slot 1: 4x minecraft:planks:1 ({label})"
    assert r["data"]["slots"][0]["name"] == "minecraft:planks:1"


def test_inventory_transfer_refuses_swap(k):
    sim = _sim(k, inventory=[{"item": "minecraft:stick", "count": 3}])
    sim.inventory.set_slot(2, "minecraft:flint", 1)
    r = sim.inventory_transfer(1, 2)
    assert r["error_code"] == "BLOCKED"
    assert r["message"] == "cannot move items from slot 1 to slot 2: slot 2 holds a different item"
    ok = sim.inventory_transfer(1, 4, 2)
    assert ok["ok"] and ok["message"] == "Moved items from slot 1 to slot 4."
    assert sim.inventory.slot(4) == ("minecraft:stick", 2) and sim.inventory.slot(1) == ("minecraft:stick", 1)


def test_equip_swaps_tool(k):
    sim = _sim(k, inventory=[{"item": "minecraft:stick", "count": 1}])
    r = sim.equip(1)
    assert r["ok"] and r["message"] == "Swapped slot 1 with the tool slot."
    assert sim.tool == "minecraft:stick" and sim.inventory.slot(1) is None
    assert sim.equip(2)["error_code"] == "NO_ITEM"


def test_craft_recipe_planks_from_log(k):
    sim = _sim(k, inventory=[{"item": "minecraft:log", "count": 1}])
    r = sim.craft_recipe(_recipe(sim, "minecraft:planks"), 1)
    assert r["ok"], r
    assert sim.inventory.count("minecraft:planks") == 4 and sim.inventory.count("minecraft:log") == 0
    slot = next(i for i in range(1, 17) if sim.inventory.slot(i) == ("minecraft:planks", 4))
    assert slot not in CRAFT_GRID
    assert r["message"].startswith(f"Crafted 1 time(s): slot {slot} now holds 4x minecraft:planks:0 (")


def test_craft_recipe_missing_lists_items(k):
    sim = _sim(k, inventory=[{"item": "minecraft:planks", "count": 1}])
    r = sim.craft_recipe(_recipe(sim, "minecraft:stick"), 1)
    assert r["error_code"] == "NO_ITEM"
    assert r["message"].startswith("not enough ingredients in the robot inventory, missing: 1x ")
    assert "(grid slot 5)" in r["message"]
    assert _total(sim) == 1


def test_craft_recipe_machine_recipe_refused(k):
    sim = _sim(k, inventory=[{"item": "minecraft:iron_ore", "count": 1}])
    r = sim.craft_recipe(_recipe(sim, "minecraft:iron_ingot"), 1)
    assert r["error_code"] == "NO_RECIPE"
    assert r["message"] == "not a crafting-table recipe (category Smelting); use nei_machine_plan for machines"


def test_craft_recipe_unknown_id(k):
    r = _sim(k).craft_recipe("r0000000000000000", 1)
    assert r["error_code"] == "NO_RECIPE" and r["message"].startswith("UNKNOWN_RECIPE: ")


def test_craft_recipe_grid_busy_inventory_full(k):
    sim = _sim(k, inventory=[{"item": "minecraft:flint", "count": 64 * 15}, {"item": "minecraft:log", "count": 1}])
    before = _total(sim)
    r = sim.craft_recipe(_recipe(sim, "minecraft:planks"), 1)
    assert r["error_code"] == "INVENTORY_FULL"
    assert _total(sim) == before


def test_craft_low_level_from_grid(k):
    sim = _sim(k)
    sim.inventory.set_slot(1, "minecraft:planks", 1)
    sim.inventory.set_slot(5, "minecraft:planks", 1)
    r = sim.craft()
    assert r["ok"] and r["message"] == "Crafted. Use inventory_scan to see the result."
    assert sim.inventory.count("minecraft:stick") == 4 and sim.inventory.count("minecraft:planks") == 0


def test_craft_low_level_empty_and_no_match(k):
    sim = _sim(k)
    r = sim.craft()
    assert r["error_code"] == "NO_ITEM"
    assert r["message"] == "crafting grid is empty (grid slots are 1,2,3 / 5,6,7 / 9,10,11)"
    sim.inventory.set_slot(1, "minecraft:flint", 1)
    sim.inventory.set_slot(2, "minecraft:stick", 1)
    r = sim.craft()
    assert r["error_code"] == "NO_RECIPE"
    assert r["message"].startswith("no recipe matches the grid, or there is no free slot for the result. Current grid:\n")


def test_nei_tools_wrap_result(k):
    sim = _sim(k)
    r = sim.nei_find("chest")
    assert r["ok"] and r["data"]["items"]
    assert json.loads(r["message"]) == r["data"]
    bad = sim.nei_recipes("nomod:nothing")
    assert bad["error_code"] == "UNKNOWN_ITEM" and bad["message"].startswith("UNKNOWN_ITEM: ")


def test_nei_craft_tree_uses_inventory(k):
    sim = _sim(k, inventory=[{"item": "minecraft:log", "count": 2}])
    with_inv = sim.nei_craft_tree("minecraft:chest", 1, True)["data"]
    without = sim.nei_craft_tree("minecraft:chest", 1, False)["data"]
    assert with_inv["raw"] == []
    assert {"item": "minecraft:log:0", "n": 2} in without["raw"]


def test_nei_machine_plan_needs_container(k):
    sim = _sim(k)
    rid = _recipe(sim, "minecraft:iron_ingot")
    r = sim.nei_machine_plan("front", rid)
    assert r["ok"] and r["data"]["put"][0]["slot"] == 1
    away = _sim(k, at_warehouse=False)
    assert away.nei_machine_plan("front", rid)["error_code"] == "BLOCKED"


def test_invalid_robot_slot_loses_nothing(k):
    """Слоты робота 1-16. Слот 17 отклоняется до любых изменений."""
    sim = _sim(k, inventory=[{"item": "minecraft:cobblestone", "count": 10}])
    chest = sim.containers[(95, 64, 105)]
    before = (_total(sim), chest.count("minecraft:cobblestone"))
    for r in (sim.inventory_transfer(1, 17), sim.storage_take("front", 1, 5, 17), sim.storage_put("front", 17),
              sim.equip(17), sim.place("front", 17), sim.craft(None, 17)):
        assert r["ok"] is False and r["error_code"] == "BLOCKED", r
        assert "invalid slot" in r["message"], r
    assert (_total(sim), chest.count("minecraft:cobblestone")) == before


def test_texts_match_oc_mcp_lua(k):
    away = _sim(k, at_warehouse=False)
    assert away.storage_scan("front")["message"] == "no storage on side front"
    sim = _sim(k, inventory=[{"item": "minecraft:stick", "count": 64}])
    sim.inventory.set_slot(2, "minecraft:flint", 1)
    assert sim.inventory_transfer(3, 1)["message"] == "cannot move items from slot 3 to slot 1: slot 3 is empty"
    assert sim.inventory_transfer(1, 2)["message"] == "cannot move items from slot 1 to slot 2: slot 2 holds a different item"
    sim.inventory.set_slot(4, "minecraft:stick", 64)
    assert sim.inventory_transfer(1, 4)["message"] == "cannot move items from slot 1 to slot 4: slot 4 is full"


def test_recipe_given_item_id_gets_hint(k):
    r = _sim(k).craft_recipe("minecraft:stick", 1)
    assert r["error_code"] == "NO_RECIPE"
    assert r["message"] == ("UNKNOWN_RECIPE: unknown recipe: minecraft:stick 'minecraft:stick' is an item id, not a "
                            "recipe id: get recipe ids (like r7fbebd0471463308) from nei_recipes.")


def test_scan_text_has_damage_like_oc_mcp(k):
    sim = _sim(k, inventory=[{"item": "minecraft:planks:1", "count": 4}])
    r = sim.inventory_scan()
    assert r["message"].startswith("slot 1: 4x minecraft:planks:1 (")
    assert r["data"]["slots"][0]["name"] == "minecraft:planks:1"
    s = sim.storage_scan("front")
    assert "slot 1: 32x minecraft:cobblestone:0 (Cobblestone)" in s["message"]
