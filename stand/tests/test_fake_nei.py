import pytest

from stand.fake_mcp.nei import CRAFT_GRID, FakeNei, NeiError, nei_id, recipe_id
from stand.knowledge import KNOWLEDGE_DIR, Knowledge


@pytest.fixture(scope="module")
def k():
    return Knowledge.load(KNOWLEDGE_DIR)


def test_nei_id_forms():
    assert nei_id("minecraft:planks") == "minecraft:planks:0"
    assert nei_id("minecraft:planks:1") == "minecraft:planks:1"


def test_craft_grid_slots():
    assert CRAFT_GRID == (1, 2, 3, 5, 6, 7, 9, 10, 11)


def test_find_by_name(k):
    r = FakeNei(k).find("cobblestone")
    assert {"item": "minecraft:cobblestone:0", "label": "Cobblestone", "mod": "minecraft"} in r["items"]
    assert r["total"] == len(r["items"])


def test_recipe_id_stable_and_recipe_roundtrip(k):
    nei = FakeNei(k)
    short = nei.recipes("minecraft:stick")["results"][0]["recipes"][0]
    assert short["id"] == nei.recipes("minecraft:stick:0")["results"][0]["recipes"][0]["id"]
    assert short["id"].startswith("r") and len(short["id"]) == 17
    full = nei.recipe(short["id"])
    assert full["overlay"] == "crafting"
    assert [(g["cell"], g["robotSlot"]) for g in full["grid"]] == [(1, 1), (4, 5)]
    assert full["out"] == [{"item": "minecraft:stick:0", "n": 4}]


def test_recipe_id_is_content_hash(k):
    r = k.get_recipes("minecraft:stick")[0]
    assert recipe_id(r) == recipe_id(dict(r))


def test_shapeless_recipe_fills_cells_in_order(k):
    nei = FakeNei(k)
    short = nei.recipes("minecraft:planks")["results"][0]["recipes"][0]
    full = nei.recipe(short["id"])
    assert [(g["cell"], g["robotSlot"], g["item"]) for g in full["grid"]] == [(1, 1, "minecraft:log:0")]


def test_machine_recipe_has_no_grid(k):
    short = FakeNei(k).recipes("minecraft:iron_ingot")["results"][0]["recipes"][0]
    assert short["overlay"] == "smelting" and short["cat"] == "Smelting"
    assert "grid" not in FakeNei(k).recipe(short["id"])


def test_craft_tree_orders_leaves_first(k):
    tree = FakeNei(k).craft_tree("minecraft:chest", 1, {"minecraft:log": 2})
    assert [s["makes"] for s in tree["steps"]] == ["minecraft:planks:0", "minecraft:chest:0"]
    assert tree["steps"][0]["runs"] == 2 and tree["raw"] == []


def test_craft_tree_ic2_machine(k):
    tree = FakeNei(k).craft_tree("IC2:blockMachine:3", 1, {})
    assert tree["steps"][-1]["makes"] == "IC2:blockMachine:3"
    assert any(m["cat"] == "Shaped Crafting" for m in tree["machinesNeeded"])
    assert tree["raw"]  # с пустым have сырьё не пустое


def test_machine_plan_slots(k):
    nei = FakeNei(k)
    rid = nei.recipes("minecraft:iron_ingot")["results"][0]["recipes"][0]["id"]
    plan = nei.machine_plan(rid)
    assert plan["put"] == [{"item": "minecraft:iron_ore:0", "n": 1, "slot": 1}]
    assert plan["take"] == [{"slot": 2}]


def test_unknown_item_and_recipe(k):
    with pytest.raises(NeiError) as e:
        FakeNei(k).recipes("nomod:nothing")
    assert str(e.value).startswith("UNKNOWN_ITEM: ")
    with pytest.raises(NeiError) as e:
        FakeNei(k).recipe("r0000000000000000")
    assert e.value.code == "UNKNOWN_RECIPE"
