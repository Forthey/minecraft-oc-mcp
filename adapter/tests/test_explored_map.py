from __future__ import annotations

from adapter.explored_map import AIR, LIQUID, SOLID, ExploredMap
from adapter.pathfinding import astar
from adapter.pose import Pose

WORLD_SCAN = "\n".join([
    "axes: x = east, z = south, y = up",
    "y=0 (rows z=0..1, columns x=0..1):",
    ". 1.5",
    "? 100.0",
])

RELATIVE_SCAN = "\n".join([
    "axes: x = right, z = forward, y = up",
    "y=0 (rows z=1..1, columns x=0..1):",
    "2.0 .",
])


def test_geo_scan_world_axes():
    m = ExploredMap()
    pose = Pose((10, 64, 10), "north")
    assert m.ingest_geo_scan(pose, {}, WORLD_SCAN) == 2
    assert m.get((11, 64, 10)).state == SOLID
    assert m.get((11, 64, 11)).state == LIQUID
    assert m.get((10, 64, 11)) is None
    assert m.get((10, 64, 10)) is None


def test_geo_scan_relative_axes():
    m = ExploredMap()
    pose = Pose((0, 64, 0), "east")
    m.ingest_geo_scan(pose, {}, RELATIVE_SCAN)
    assert m.get((1, 64, 0)).state == SOLID
    assert m.get((1, 64, 1)).state == AIR


def test_surroundings_names():
    m = ExploredMap()
    pose = Pose((0, 64, 0), "north")
    text = "\n".join([
        "front: minecraft:stone (solid) hardness 1.5",
        "back: (air)",
        "up: minecraft:planks:2 (solid) hardness 2.0",
        "down: minecraft:lava (liquid) hardness 100.0",
        "left: unknown",
    ])
    seen = m.ingest_surroundings(pose, text)
    assert len(seen) == 4
    assert m.get((0, 64, -1)).name == "minecraft:stone"
    assert m.get((0, 64, 1)).state == AIR
    assert m.get((0, 65, 0)).name == "minecraft:planks:2"
    assert m.get((0, 63, 0)).state == LIQUID


def test_geo_scan_keeps_known_name():
    m = ExploredMap()
    pose = Pose((0, 64, 0), "north")
    m.ingest_surroundings(pose, "front: minecraft:stone (solid)")
    m.ingest_geo_scan(pose, {}, "axes: x = east, z = south, y = up\ny=0 (rows z=-1..-1, columns x=0..0):\n1.4")
    assert m.get((0, 64, -1)).name == "minecraft:stone"


def test_move_events():
    m = ExploredMap()
    pose = Pose((0, 64, 0), "north")
    m.on_move_blocked(pose, "forward")
    assert m.occupied((0, 64, -1))
    m.on_moved(pose)
    assert not m.occupied((0, 64, 0))
    m.on_place(pose, "up", "minecraft:cobblestone")
    assert m.get((0, 65, 0)).name == "minecraft:cobblestone"
    m.on_swing(pose, "up")
    assert not m.occupied((0, 65, 0))


def test_verify_missing_wrong_unverified():
    m = ExploredMap()
    m.mark((0, 0, 0), SOLID, "minecraft:stone")
    m.mark((1, 0, 0), SOLID, "minecraft:dirt")
    m.mark((2, 0, 0), SOLID)
    missing, wrong = m.verify([
        {"pos": [0, 0, 0], "item": "minecraft:stone:0"},
        {"pos": [1, 0, 0], "item": "minecraft:stone"},
        {"pos": [2, 0, 0], "item": "minecraft:stone"},
        {"pos": [3, 0, 0], "item": "minecraft:stone"},
    ])
    assert [e["pos"] for e in missing] == [[3, 0, 0]]
    assert [e["pos"] for e in wrong] == [[1, 0, 0]]
    assert [e["pos"] for e in m.last_unverified] == [[2, 0, 0]]


def test_region_radius():
    m = ExploredMap(radius=2)
    assert not m.region_contains((0, 0, 0))
    m.mark((0, 0, 0), AIR)
    assert m.region_contains((2, 0, 0))
    assert not m.region_contains((3, 0, 0))
    assert ExploredMap().region_contains((999, 0, 0))


def test_persistence(tmp_path):
    db = tmp_path / "map.db"
    m = ExploredMap("w1", db)
    m.mark((1, 2, 3), SOLID, "minecraft:stone")
    m.flush()
    assert ExploredMap("w1", db).get((1, 2, 3)).name == "minecraft:stone"
    assert ExploredMap("w2", db).get((1, 2, 3)) is None


class Hazards:
    def __init__(self, cells):
        self.cells = set(cells)

    def in_hazard(self, p):
        return p in self.cells


def _cost(m):
    return lambda p: None if m.occupied(p) or not (-1 <= p[1] <= 1) or not (-3 <= p[2] <= 3) else 1


def test_astar_avoids_solid_and_hazard():
    m = ExploredMap(hazards=Hazards({(1, 0, 1)}))
    for y in (-1, 0, 1):
        m.mark((1, y, 0), SOLID)
    path = astar((0, 0, 0), (2, 0, 0), _cost(m))
    assert path is not None
    assert all(not m.occupied(p) for p in path)
    assert (1, 0, 1) not in path
