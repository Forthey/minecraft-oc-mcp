import copy

import pytest

from stand.fake_mcp.inventory import Container, Inventory
from stand.fake_mcp.sim import RobotSim
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.scenario import SCENARIOS_DIR, load_scenario
from stand.world.backend import MemoryWorld

WAREHOUSE = (95, 64, 105)
NEXT_TO_WAREHOUSE = (96, 64, 105)


@pytest.fixture(scope="module")
def k():
    return Knowledge.load(KNOWLEDGE_DIR)


def _sim(k, sid="s01-wall", inventory=None, at_warehouse=True):
    s = copy.deepcopy(load_scenario(SCENARIOS_DIR / sid / "scenario.yaml"))
    if inventory is not None:
        s.robot["inventory"] = inventory
    if at_warehouse:
        s.robot["pos"] = NEXT_TO_WAREHOUSE
        s.robot["facing"] = "west"
    world = MemoryWorld(s.scene_blocks())
    return RobotSim(s, Knowledge.load(KNOWLEDGE_DIR, s.knowledge), world), world


def test_inventory_add_remove_stacks():
    inv = Inventory(slots=2, stack=64)
    assert inv.add("a", 100) == 0
    assert inv.add("a", 40) == 12
    assert inv.count("a") == 128
    assert not inv.remove("a", 200) and inv.count("a") == 128
    assert inv.remove("a", 70) and inv.count("a") == 58


def test_container_slots():
    c = Container(3)
    assert c.put_slot(1, "x", 5) == 0
    assert c.put_slot(1, "y", 1) == 1
    assert c.take_slot(1, "x", 3) == 3 and c.count("x") == 2
    assert c.take_slot(0, "x", 1) == 0


def test_take_from_warehouse_moves_items(k):
    sim, _ = _sim(k)
    r = sim.take("front", "minecraft:cobblestone", 9)
    assert r["ok"] and r["data"]["moved"] == 9
    assert sim.inventory.count("minecraft:cobblestone") == 9
    assert sim.containers[WAREHOUSE].count("minecraft:cobblestone") == 23


def test_take_missing_item(k):
    sim, _ = _sim(k)
    assert sim.take("front", "minecraft:planks", 1)["error_code"] == "NO_ITEM"
    assert sim.take("front", "minecraft:cobblestone", 33)["error_code"] == "NO_ITEM"
    assert sim.take("front", "nomod:thing", 1)["error_code"] == "UNKNOWN_ITEM"


def test_take_wrong_side_blocked(k):
    sim, _ = _sim(k)
    r = sim.take("back", "minecraft:cobblestone", 1)
    assert r["error_code"] == "BLOCKED" and "no container" in r["message"]


def test_inventory_full(k):
    full = [{"item": "minecraft:dirt", "count": 64}] * 16
    sim, _ = _sim(k, inventory=full)
    assert sim.take("front", "minecraft:cobblestone", 1)["error_code"] == "INVENTORY_FULL"
    assert sim.containers[WAREHOUSE].count("minecraft:cobblestone") == 32


def test_put_back_and_inspect_container(k):
    sim, _ = _sim(k)
    sim.take("front", "minecraft:cobblestone", 10)
    assert sim.put("front", "minecraft:cobblestone", 4)["ok"]
    d = sim.inspect_container("front")["data"]
    assert d["block"] == "minecraft:chest" and d["size"] == 27
    assert sum(s["count"] for s in d["slots"]) == 26
    assert sim.put("front", "minecraft:cobblestone", 50)["error_code"] == "NO_ITEM"
    assert sim.inspect_container("back")["error_code"] == "BLOCKED"


def test_craft_planks_from_log(k):
    sim, _ = _sim(k, inventory=[{"item": "minecraft:log", "count": 2}])
    r = sim.craft("minecraft:planks", 5)
    assert r["ok"] and r["data"]["crafted"] == 8
    assert sim.inventory.count("minecraft:planks") == 8
    assert sim.inventory.count("minecraft:log") == 0


def test_craft_missing_ingredient(k):
    sim, _ = _sim(k, inventory=[{"item": "minecraft:planks", "count": 3}])
    r = sim.craft("minecraft:chest", 1)
    assert r["error_code"] == "NO_ITEM"
    assert r["data"]["missing"] == [{"item": "minecraft:planks", "count": 5}]
    assert sim.inventory.count("minecraft:planks") == 3


def test_craft_machine_only_no_recipe(k):
    sim, _ = _sim(k, inventory=[{"item": "minecraft:iron_ore", "count": 1}])
    assert sim.craft("minecraft:iron_ingot", 1)["error_code"] == "NO_RECIPE"
    assert sim.craft("nomod:thing", 1)["error_code"] == "UNKNOWN_ITEM"


def test_craft_inventory_full_rolls_back(k):
    # Бревно уходит целиком, слот освобождается, доски помещаются.
    inv = [{"item": "minecraft:log", "count": 1}] + [{"item": "minecraft:dirt", "count": 64}] * 15
    sim, _ = _sim(k, inventory=inv)
    assert sim.craft("minecraft:planks", 4)["ok"]
    # Из двух брёвен уходит одно, слот остаётся занят, доскам места нет.
    inv = [{"item": "minecraft:log", "count": 2}] + [{"item": "minecraft:dirt", "count": 64}] * 15
    sim, _ = _sim(k, inventory=inv)
    assert sim.craft("minecraft:planks", 4)["error_code"] == "INVENTORY_FULL"
    assert sim.inventory.count("minecraft:log") == 2
    assert sim.inventory.count("minecraft:planks") == 0


def test_put_into_machine_slot(k):
    sim, world = _sim(k, inventory=[{"item": "IC2:blockMachine:3", "count": 1},
                                    {"item": "minecraft:iron_ore", "count": 2}], at_warehouse=False)
    assert sim.place("IC2:blockMachine:3", "front")["ok"]
    r = sim.put("front", "minecraft:iron_ore", 1, slot=0)
    assert r["ok"], r
    d = sim.inspect_container("front")["data"]
    assert d["block"] == "IC2:blockMachine:3"
    assert d["slots"] == [{"slot": 0, "item": "minecraft:iron_ore", "count": 1}]
    assert sim.put("front", "minecraft:iron_ore", 1, slot=9)["error_code"] == "BLOCKED"


def test_plan_materials_counts_warehouse(k):
    sim, _ = _sim(k, "s04-ic2-machines", inventory=[])
    d = sim.plan_materials("IC2:blockGenerator", 1)["data"]
    assert d["missing"] == []
    d = sim.plan_materials("IC2:blockGenerator", 1, use_inventory=False)["data"]
    assert {m["item"] for m in d["missing"]} >= {"IC2:itemBatRE"}


def test_knowledge_tools(k):
    sim, _ = _sim(k)
    assert sim.search_items("macerator")["data"]["items"][0]["item"] == "IC2:blockMachine:3"
    assert sim.get_item("minecraft:planks:0")["data"]["item"] == "minecraft:planks"
    assert sim.get_item("nomod:x")["error_code"] == "UNKNOWN_ITEM"
    recipes = sim.get_recipes("IC2:blockGenerator")["data"]["recipes"]
    assert recipes[0]["grid"][1] == ["IC2:itemPlates:4"] * 3
    assert sim.search_docs("power macerator generator")["data"]["docs"][0]["doc_id"] in ("ic2-macerator", "ic2-generator")


def test_verify_blocks_missing_and_wrong(k):
    sim, world = _sim(k, inventory=[{"item": "minecraft:cobblestone", "count": 2}], at_warehouse=False)
    sim.place_at(100, 64, 100, "minecraft:cobblestone")
    world.set_block((101, 64, 100), ("minecraft:planks", 0))
    expected = [
        {"pos": [100, 64, 100], "item": "minecraft:cobblestone"},
        {"pos": [101, 64, 100], "item": "minecraft:cobblestone"},
        {"pos": [102, 64, 100], "item": "minecraft:cobblestone"},
        {"pos": [95, 64, 105], "item": "minecraft:chest"},
    ]
    d = sim.verify_blocks(expected)["data"]
    assert d["checked"] == 4
    assert d["missing"] == [{"pos": [102, 64, 100], "item": "minecraft:cobblestone"}]
    assert d["wrong"] == [{"pos": [101, 64, 100], "item": "minecraft:cobblestone"}]
    assert d["next_page"] is None


def test_verify_blocks_pages(k):
    sim, _ = _sim(k)
    expected = [{"pos": [100, 64, 100 - i], "item": "minecraft:air"} for i in range(60)]
    first = sim.verify_blocks(expected)["data"]
    assert first["checked"] == 50 and first["next_page"] == 1
    second = sim.verify_blocks(expected, page=1)["data"]
    assert second["checked"] == 10 and second["next_page"] is None


def test_read_block_info_blocked(k):
    sim, _ = _sim(k)
    r = sim.read_block_info("front")
    assert r["error_code"] == "BLOCKED" and "not supported" in r["message"]


def test_equip_and_drop(k):
    sim, _ = _sim(k, inventory=[{"item": "minecraft:stick", "count": 3}])
    assert sim.equip("minecraft:stick")["ok"]
    assert sim.get_status()["data"]["tool"]["item"] == "minecraft:stick"
    assert sim.inventory.count("minecraft:stick") == 2
    assert sim.drop("minecraft:stick", 2)["ok"]
    assert sim.drop("minecraft:stick", 1)["error_code"] == "NO_ITEM"
    assert sim.equip("minecraft:planks")["error_code"] == "NO_ITEM"


def test_stop(k):
    sim, _ = _sim(k)
    assert sim.stop()["ok"]


def test_landmark_chest_is_empty_container(k):
    s = copy.deepcopy(load_scenario(SCENARIOS_DIR / "s08-landmark" / "scenario.yaml"))
    s.robot["pos"] = (105, 64, 101)
    sim = RobotSim(s, k, MemoryWorld(s.scene_blocks()))
    d = sim.inspect_container("front")["data"]
    assert d["block"] == "minecraft:chest" and d["slots"] == []
