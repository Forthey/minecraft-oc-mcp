import json

import pytest

from stand.knowledge import Knowledge, KNOWLEDGE_DIR


@pytest.fixture
def k():
    return Knowledge.load(KNOWLEDGE_DIR)


def _mini(tmp_path, items, recipes, docs=()):
    d = tmp_path / "kn"
    d.mkdir()
    (d / "items.json").write_text(json.dumps(items))
    (d / "recipes.json").write_text(json.dumps(recipes))
    (d / "docs.json").write_text(json.dumps(list(docs)))
    return Knowledge.load(d)


def _shapeless(output, count, ingredients):
    return {"type": "crafting_shapeless", "output": {"item": output, "count": count}, "ingredients": ingredients}


def test_block_for_and_back(k):
    assert k.block_for("minecraft:planks:1") == ("minecraft:planks", 1)
    assert k.block_for("minecraft:stick") is None
    assert k.item_for(("minecraft:log", 0)) == "minecraft:log"
    assert k.item_for(("IC2:blockMachine", 3)) == "IC2:blockMachine:3"


def test_item_for_ignores_masked_meta(k):
    # Сундук сам поворачивается (meta 0 становится 3), бревно хранит ось в старших битах.
    assert k.item_for(("minecraft:chest", 3)) == "minecraft:chest"
    assert k.item_for(("minecraft:log", 1 | 4)) == "minecraft:log:1"


def test_block_matches_uses_meta_mask(k):
    assert k.block_matches(("minecraft:chest", 0), ("minecraft:chest", 3))
    assert k.block_matches(("minecraft:log", 1), ("minecraft:log", 1 | 8))
    assert not k.block_matches(("minecraft:log", 1), ("minecraft:log", 2))
    assert not k.block_matches(("minecraft:planks", 0), ("minecraft:planks", 1))
    assert not k.block_matches(("minecraft:planks", 0), ("minecraft:cobblestone", 0))
    # Неизвестный блок сравнивается строго.
    assert not k.block_matches(("nomod:thing", 0), ("nomod:thing", 1))


def test_id_normalization(k):
    assert k.get_item("minecraft:planks:0")["item"] == "minecraft:planks"
    assert k.get_item("nomod:nothing") is None


def test_plan_materials_uses_have(k):
    assert k.plan_materials("minecraft:planks", 4, {"minecraft:log": 1})["missing"] == []
    assert k.plan_materials("minecraft:planks", 4, {})["missing"] == [
        {"item": "minecraft:log", "count": 1, "craftable": False}
    ]


def test_plan_materials_rounds_crafts_up(k):
    # 5 досок требуют двух крафтов, то есть двух брёвен.
    assert k.plan_materials("minecraft:planks", 5, {})["missing"] == [
        {"item": "minecraft:log", "count": 2, "craftable": False}
    ]


def test_plan_materials_tree_shape(k):
    plan = k.plan_materials("minecraft:chest", 1, {"minecraft:log": 2})
    assert plan["missing"] == []
    tree = plan["tree"]
    assert tree["item"] == "minecraft:chest" and tree["count"] == 1
    assert tree["children"][0]["item"] == "minecraft:planks"
    assert tree["children"][0]["count"] == 8


def test_machine_recipe_not_craftable(tmp_path):
    k = _mini(
        tmp_path,
        [{"id": "a:dust", "name": "Dust", "mod": "a"}, {"id": "a:ore", "name": "Ore", "mod": "a"}],
        [{"type": "machine", "machine": "a:mill", "output": {"item": "a:dust", "count": 2},
          "ingredients": {"a:ore": 1}}],
    )
    assert k.plan_materials("a:dust", 2, {})["missing"] == [
        {"item": "a:dust", "count": 2, "craftable": False}
    ]


def test_plan_materials_cycle_guard(tmp_path):
    k = _mini(
        tmp_path,
        [{"id": "a:x", "name": "X", "mod": "a"}, {"id": "a:y", "name": "Y", "mod": "a"}],
        [_shapeless("a:x", 1, {"a:y": 1}), _shapeless("a:y", 1, {"a:x": 1})],
    )
    missing = k.plan_materials("a:x", 1, {})["missing"]
    assert [m["item"] for m in missing] == ["a:x"]


def test_search_docs_mod_filter_and_rank(tmp_path):
    k = _mini(tmp_path, [], [], [
        {"doc_id": "d1", "title": "Generator", "mod": "IC2", "version": "v", "text": "generator makes power"},
        {"doc_id": "d2", "title": "Macerator power", "mod": "IC2", "version": "v",
         "text": "connect the macerator to a generator for power"},
        {"doc_id": "d3", "title": "Robot", "mod": "OpenComputers", "version": "v", "text": "robot power"},
    ])
    hits = k.search_docs("macerator generator power")
    assert [h["doc_id"] for h in hits][:2] == ["d2", "d1"]
    assert "text" not in hits[0] and hits[0]["snippet"]
    assert [h["doc_id"] for h in k.search_docs("power", mod="opencomputers")] == ["d3"]
    assert k.search_docs("zzz") == []


def test_search_items(k):
    hits = k.search_items("macerator")
    assert hits[0]["item"] == "IC2:blockMachine:3"
    assert set(hits[0]) == {"item", "name", "mod"}


def test_extra_overrides(tmp_path):
    base = _mini(tmp_path, [{"id": "a:x", "name": "X", "mod": "a"}, {"id": "a:y", "name": "Y", "mod": "a"}], [])
    k = Knowledge.load(base.base_dir, extra={"recipes": [_shapeless("a:x", 1, {"a:y": 2})]})
    assert k.plan_materials("a:x", 1, {"a:y": 2})["missing"] == []
    assert len(k.get_recipes("a:x")) == 1


def test_fixtures_consistent(k):
    """Все предметы из рецептов есть в items.json, у рецептов есть выход."""
    for r in k.recipes:
        assert k.get_item(r["output"]["item"]) is not None, r["output"]
        for ing in r["ingredients"]:
            assert k.get_item(ing) is not None, ing


def test_s04_machines_craftable_from_parts(k):
    have = {
        "IC2:itemPlates:4": 16, "minecraft:furnace": 1, "IC2:itemBatRE": 1,
        "IC2:itemPartCircuit": 1, "minecraft:flint": 3, "minecraft:cobblestone": 2,
    }
    assert k.plan_materials("IC2:blockGenerator", 1, have)["missing"] == []
    # Обе машины вместе из одного набора: 16 пластин ровно на корпус, печь и генератор.
    both = {"IC2:blockGenerator": 1, "IC2:blockMachine:3": 1}
    assert k.plan_many(both, have)["missing"] == []
    short = dict(have, **{"IC2:itemPlates:4": 15})
    assert k.plan_many(both, short)["missing"] == [
        {"item": "IC2:itemPlates:4", "count": 1, "craftable": False}
    ]


def test_plan_does_not_mutate_have(k):
    have = {"minecraft:log": 1}
    k.plan_materials("minecraft:planks", 4, have)
    assert have == {"minecraft:log": 1}
