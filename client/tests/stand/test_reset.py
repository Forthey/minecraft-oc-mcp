import copy

import pytest

from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.runner.reset import prepare_scene, reset_region, warehouse_nbt
from stand.scenario import SCENARIOS_DIR, load_scenario
from stand.world.backend import MemoryWorld
from stand.world.snapshot import Snapshot


@pytest.fixture(scope="module")
def k():
    return Knowledge.load(KNOWLEDGE_DIR)


def _snapshot_of(world, box):
    return lambda: Snapshot(box, {p: b for p, b in world.blocks.items() if box.contains(p)})


def test_reset_region_memory(k):
    s = load_scenario(SCENARIOS_DIR / "s01-wall" / "scenario.yaml")
    world = MemoryWorld({
        (100, 64, 100): ("minecraft:cobblestone", 0),
        (100, 65, 100): ("minecraft:cobblestone", 0),
        (100, 63, 101): ("minecraft:air", 0),
        (95, 64, 105): ("minecraft:chest", 3),
    })
    assert reset_region(world, _snapshot_of(world, s.region), s, k) is True
    assert world.blocks == {}


def test_reset_clears_containers_before_removal(k):
    s = load_scenario(SCENARIOS_DIR / "s01-wall" / "scenario.yaml")
    world = MemoryWorld({(95, 64, 105): ("minecraft:chest", 3), (101, 64, 100): ("IC2:blockMachine", 3)})
    reset_region(world, _snapshot_of(world, s.region), s, k)
    cleared = [p for p, _, nbt in world.nbt_log if nbt == "{Items:[]}"]
    assert set(cleared) == {(95, 64, 105), (101, 64, 100)}


def test_reset_reports_failure(k):
    s = load_scenario(SCENARIOS_DIR / "s01-wall" / "scenario.yaml")

    class StubbornWorld(MemoryWorld):
        def set_block(self, p, b):
            pass

    world = StubbornWorld({(100, 64, 100): ("minecraft:cobblestone", 0)})
    assert reset_region(world, _snapshot_of(world, s.region), s, k) is False


def test_prepare_scene(k):
    s = load_scenario(SCENARIOS_DIR / "s03-obstacle" / "scenario.yaml")
    world = MemoryWorld()
    prepare_scene(world, s, k, item_ids={"minecraft:cobblestone": 4})
    assert world.get((99, 64, 99)) == ("minecraft:stone", 0)
    assert world.get((100, 64, 100)) == ("minecraft:air", 0)
    assert world.get((95, 64, 105)) == ("minecraft:chest", 0)
    p, block, nbt = world.nbt_log[-1]
    assert p == (95, 64, 105) and "id:4s" in nbt and "Count:32b" in nbt


def test_warehouse_nbt_splits_stacks():
    nbt = warehouse_nbt({"minecraft:cobblestone": 100, "IC2:itemPlates:4": 16},
                        {"minecraft:cobblestone": 4, "IC2:itemPlates": 4104})
    assert nbt == ("{Items:[{Slot:0b,id:4s,Count:64b,Damage:0s},{Slot:1b,id:4s,Count:36b,Damage:0s},"
                   "{Slot:2b,id:4104s,Count:16b,Damage:4s}]}")


def test_warehouse_nbt_unknown_item_raises():
    with pytest.raises(KeyError, match="nomod:thing"):
        warehouse_nbt({"nomod:thing": 1}, {})
