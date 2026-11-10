import pytest

from stand.judge import judge
from stand.judge.patterns import candidates, rotate
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.scenario import SCENARIOS_DIR, expand_fill, load_scenario
from stand.world.snapshot import Snapshot

COBBLE = "minecraft:cobblestone"
PLANKS = "minecraft:planks"


@pytest.fixture(scope="module")
def k():
    return Knowledge.load(KNOWLEDGE_DIR)


def _scenario(sid):
    return load_scenario(SCENARIOS_DIR / sid / "scenario.yaml")


def _wall(x0, z, block=COBBLE, along="x"):
    """Стена 3x3 от (x0, 64, z) вдоль X или вдоль Z."""
    if along == "x":
        return expand_fill([{"from": [x0, 64, z], "to": [x0 + 2, 66, z], "block": block}])
    return expand_fill([{"from": [x0, 64, z], "to": [x0, 66, z + 2], "block": block}])


def _world(s, *walls, extra=None):
    blocks = {}
    for p, b in s.scene_blocks().items():
        # Сундуки в мире сами поворачиваются, meta меняется.
        blocks[p] = (b[0], 3) if b[0] == "minecraft:chest" else b
    for w in walls:
        blocks.update(w)
    blocks.update(extra or {})
    return Snapshot(s.region, blocks)


def _judge(s, k, *walls, extra=None):
    return judge(_world(s, *walls, extra=extra), s, k)


def test_rotate_90():
    b = ("minecraft:stone", 0)
    assert set(rotate({(0, 0, 0): b, (1, 0, 0): b}, 90)) == {(0, 0, 0), (0, 0, 1)}
    assert set(rotate({(0, 0, 0): b, (1, 0, 0): b}, 180)) == {(0, 0, 0), (1, 0, 0)}
    assert rotate({(0, 0, 0): b}, 0) == {(0, 0, 0): b}


def test_candidates_cover_built_wall():
    pattern = _wall(0, 0)
    pattern = {(x, y - 64, z): b for (x, y, z), b in pattern.items()}
    built = _wall(100, 102)
    origins = {(pl.origin, pl.rotation) for pl in candidates(pattern, [0], built)}
    assert ((100, 64, 102), 0) in origins


def test_offset_interpretation(k):
    s = _scenario("s07-relative")
    out = _judge(s, k, _wall(100, 102), _wall(95, 102))
    assert out["passed"], out
    st = out["details"]["structures"]
    assert st["A"]["anchor_ok"] and st["A"]["origin"] == [100, 64, 102]
    assert st["B"]["interpretation"] == "offset" and st["B"]["offset"] == [-5, 0, 0]
    assert out["accuracy"] == 1.0 and out["extra_count"] == 0


def test_gap_interpretation(k):
    s = _scenario("s07-relative")
    out = _judge(s, k, _wall(100, 102), _wall(92, 102))
    assert out["passed"], out
    assert out["details"]["structures"]["B"]["interpretation"] == "gap of 5"


def test_wrong_direction_reported(k):
    s = _scenario("s07-relative")
    out = _judge(s, k, _wall(100, 102), _wall(105, 102))
    assert not out["passed"]
    b = out["details"]["structures"]["B"]
    assert b["interpretation"] == "other"
    assert b["offset"] == [5, 0, 0]
    assert b["found"] is True
    assert out["extra_count"] == 0


def test_anchor_too_far(k):
    s = _scenario("s07-relative")
    out = _judge(s, k, _wall(100, 95), _wall(95, 95))
    assert not out["passed"]
    assert out["details"]["structures"]["A"]["anchor_ok"] is False


def test_rotated_wall_found(k):
    s = _scenario("s07-relative")
    # Стена A вдоль Z прямо перед роботом, B на 5 западнее с тем же поворотом.
    out = _judge(s, k, _wall(100, 101, along="z"), _wall(95, 101, along="z"))
    a = out["details"]["structures"]["A"]
    assert a["rotation"] in (90, 270) and a["found"]
    assert out["passed"], out


def test_partial_wall_accuracy(k):
    s = _scenario("s07-relative")
    a = _wall(100, 102)
    del a[(101, 65, 102)]
    out = _judge(s, k, a, _wall(95, 102))
    st = out["details"]["structures"]["A"]
    assert st["accuracy"] == pytest.approx(8 / 9)
    assert st["found"] is False
    assert not out["passed"]


def test_nothing_built(k):
    s = _scenario("s07-relative")
    out = _judge(s, k)
    assert not out["passed"]
    assert out["details"]["structures"]["A"]["found"] is False
    assert out["details"]["structures"]["A"]["origin"] is None
    assert out["accuracy"] == 0.0


def test_extra_outside_structures(k):
    s = _scenario("s07-relative")
    out = _judge(s, k, _wall(100, 102), _wall(95, 102), extra={(110, 64, 95): ("minecraft:cobblestone", 0)})
    assert out["extra_count"] == 1
    assert not out["passed"]


def test_near_block_left_of_chest(k):
    s = _scenario("s08-landmark")
    # Стена из досок вдоль X, правый край в одном блоке западнее сундука в (105, 64, 100).
    west = _judge(s, k, _wall(102, 100, block=PLANKS))
    assert west["passed"], west
    west_gap = _judge(s, k, _wall(101, 100, block=PLANKS))
    assert west_gap["passed"], west_gap
    east = _judge(s, k, _wall(106, 100, block=PLANKS))
    assert not east["passed"]
    assert east["details"]["structures"]["wall"]["anchor_ok"] is False
    too_far = _judge(s, k, _wall(100, 100, block=PLANKS))
    assert not too_far["passed"]


def test_absolute_and_any_side(k):
    s = _scenario("s04-ic2-machines")
    mac = {(100, 64, 100): ("IC2:blockMachine", 3)}
    gen_north = {(100, 64, 99): ("IC2:blockGenerator", 0)}
    out = judge(_world(s, mac, gen_north), s, k)
    assert out["passed"], out
    assert out["details"]["structures"]["generator"]["interpretation"] == "north"
    gen_far = {(103, 64, 100): ("IC2:blockGenerator", 0)}
    out = judge(_world(s, mac, gen_far), s, k)
    assert not out["passed"]
    assert out["details"]["structures"]["generator"]["interpretation"] == "other"
    assert out["details"]["structures"]["generator"]["offset"] == [3, 0, 0]


def test_macerator_elsewhere_fails(k):
    s = _scenario("s04-ic2-machines")
    out = judge(_world(s, {(101, 64, 100): ("IC2:blockMachine", 3)}, {(102, 64, 100): ("IC2:blockGenerator", 0)}), s, k)
    assert not out["passed"]
    assert out["details"]["structures"]["macerator"]["found"] is False
