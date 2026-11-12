from __future__ import annotations

import pytest

from adapter.explored_map import ExploredMap
from adapter.memory_link import MemoryLink

pytest.importorskip("memory_mcp")


@pytest.fixture
def link(tmp_path):
    link = MemoryLink("w1", robot_id="r1", db_path=tmp_path / "memory.db")
    yield link
    link.close()


def _poi(link, kind, x, y, z, radius=0, label="p"):
    from memory_mcp.schemas import PoiRecord

    link.repo.remember_poi(link._ctx(), PoiRecord(kind=kind, label=label, dim=0, x=x, y=y, z=z, radius=radius))
    link._loaded_at = 0.0


def test_disabled_without_db(monkeypatch):
    monkeypatch.delenv("MEMORY_DB", raising=False)
    link = MemoryLink("w1")
    assert not link.enabled
    assert link.hazards() == []
    assert link.route_hint((0, 64, 0), (100, 64, 0)) == []
    assert link.report_hazard((0, 64, 0), "minecraft:lava") is None


def test_hazard_blocks_map_cell(link):
    _poi(link, "hazard", 10, 64, 10, radius=1, label="lava pool")
    m = ExploredMap(hazards=link)
    assert m.occupied((11, 64, 9))
    assert not m.occupied((12, 64, 10))


def test_waypoints_route_hint(link):
    _poi(link, "waypoint", 50, 64, 0, label="mid")
    _poi(link, "waypoint", -50, 64, 0, label="behind")
    assert link.route_hint((0, 64, 0), (100, 64, 0)) == [(50, 64, 0)]


def test_report_hazard(link):
    assert link.report_hazard((5, 64, 5), "minecraft:stone") is None
    assert link.report_hazard((5, 64, 5), "minecraft:lava") is not None
    assert link.in_hazard((5, 64, 6))


def test_other_world_not_visible(link, tmp_path):
    _poi(link, "hazard", 0, 64, 0, radius=2)
    other = MemoryLink("w2", db_path=tmp_path / "memory.db")
    try:
        assert not other.in_hazard((0, 64, 0))
    finally:
        other.close()
