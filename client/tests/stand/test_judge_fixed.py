import pytest

from stand.judge import judge
from stand.judge.fixed import judge_fixed
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.scenario import SCENARIOS_DIR, expand_fill, load_scenario
from stand.world.blocks import AIR
from stand.world.snapshot import Box, Snapshot

COBBLE = ("minecraft:cobblestone", 0)
PLANKS = ("minecraft:planks", 0)
REGION = Box((90, 63, 90), (115, 72, 110))
WALL = expand_fill([{"from": [100, 64, 100], "to": [102, 66, 100], "block": "minecraft:cobblestone"}])
CHEST_POS = (95, 64, 105)
SCENE = {CHEST_POS: ("minecraft:chest", 0)}
SCORING = {"pass_accuracy": 1.0, "max_extra": 0}


@pytest.fixture(scope="module")
def k():
    return Knowledge.load(KNOWLEDGE_DIR)


def _snap(blocks):
    # Сундук склада в мире: meta 3, потому что он сам повернулся при установке.
    return Snapshot(REGION, {CHEST_POS: ("minecraft:chest", 3), **blocks})


def _judge(k, blocks, scene=SCENE, removable=frozenset(), scoring=SCORING):
    return judge_fixed(_snap(blocks), WALL, scene, set(removable), scoring, k)


def test_perfect_wall_passes(k):
    r = _judge(k, dict(WALL))
    assert r.passed and r.accuracy == 1.0
    assert (r.correct, r.total) == (9, 9)
    assert r.missing == [] and r.wrong == [] and r.extra == []


def test_missing_and_wrong(k):
    blocks = dict(WALL)
    del blocks[(100, 64, 100)]
    blocks[(101, 64, 100)] = PLANKS
    r = _judge(k, blocks)
    assert r.missing == [(100, 64, 100)]
    assert r.wrong == [((101, 64, 100), COBBLE, PLANKS)]
    assert r.accuracy == pytest.approx(7 / 9)
    assert not r.passed


def test_extra_block_fails_with_max_extra_0(k):
    r = _judge(k, {**WALL, (105, 64, 100): COBBLE})
    assert r.accuracy == 1.0
    assert r.extra == [((105, 64, 100), COBBLE)]
    assert not r.passed
    assert _judge(k, {**WALL, (105, 64, 100): COBBLE}, scoring={"pass_accuracy": 1.0, "max_extra": 1}).passed


def test_setup_blocks_not_extra(k):
    scene = {**SCENE, (98, 64, 98): ("minecraft:stone", 0)}
    r = _judge(k, {**WALL, (98, 64, 98): ("minecraft:stone", 0)}, scene=scene)
    assert r.passed and r.extra == []


def test_rotated_chest_not_extra(k):
    """Сундук склада сам поменял meta с 0 на 3, это не изменение сцены."""
    r = _judge(k, dict(WALL))
    assert r.extra == []


def test_broken_floor_is_extra(k):
    r = _judge(k, {**WALL, (100, 63, 101): AIR})
    assert r.extra == [((100, 63, 101), AIR)]
    assert not r.passed


def test_removed_setup_block_is_extra(k):
    scene = {**SCENE, (98, 64, 98): ("minecraft:stone", 0)}
    r = _judge(k, dict(WALL), scene=scene)
    assert r.extra == [((98, 64, 98), AIR)]


def test_removable_block_may_be_broken(k):
    scene = {**SCENE, (98, 64, 98): ("minecraft:stone", 0), (98, 65, 98): ("minecraft:stone", 0)}
    removable = {(98, 64, 98), (98, 65, 98)}
    r = _judge(k, {**WALL, (98, 65, 98): ("minecraft:stone", 0)}, scene=scene, removable=removable)
    assert r.passed and r.extra == []
    # На месте removable-блока поставлено что-то другое: это лишнее изменение.
    r = _judge(k, {**WALL, (98, 64, 98): COBBLE}, scene=scene, removable=removable)
    assert r.extra == [((98, 64, 98), COBBLE)]


def test_expected_inside_removable_counts_normally(k):
    """В s03 место стены пустое внутри короба: ожидаемые блоки проверяются как обычно."""
    s = load_scenario(SCENARIOS_DIR / "s03-obstacle" / "scenario.yaml")
    world = {p: b for p, b in s.scene_blocks().items() if b != AIR}
    world[CHEST_POS] = ("minecraft:chest", 3)
    for p in [(99, 64, 100), (99, 65, 100), (100, 65, 101)]:
        world[p] = AIR
    world.update(WALL)
    out = judge(Snapshot(s.region, world), s, k)
    assert out["passed"], out
    assert out["extra_count"] == 0


def test_judge_dispatch_fixed(k):
    s = load_scenario(SCENARIOS_DIR / "s01-wall" / "scenario.yaml")
    out = judge(_snap(dict(WALL)), s, k)
    assert out["mode"] == "fixed"
    assert out["passed"] is True
    assert out["accuracy"] == 1.0
    assert out["extra_count"] == 0
    assert out["details"]["correct"] == 9


def test_judge_result_is_json_serializable(k):
    import json

    s = load_scenario(SCENARIOS_DIR / "s01-wall" / "scenario.yaml")
    blocks = dict(WALL)
    blocks[(101, 64, 100)] = PLANKS
    out = judge(_snap(blocks), s, k)
    back = json.loads(json.dumps(out))
    assert back["details"]["wrong"] == [{"pos": [101, 64, 100], "expected": "minecraft:cobblestone",
                                         "actual": "minecraft:planks"}]


def test_robot_block_is_not_extra(k):
    """Настоящий робот OpenComputers стоит в регионе блоком, а в движении оставляет afterimage."""
    blocks = {**WALL, (100, 64, 103): ("OpenComputers:robot", 2), (100, 65, 103): ("OpenComputers:robotAfterimage", 0)}
    r = _judge(k, blocks)
    assert r.passed and r.extra == []
