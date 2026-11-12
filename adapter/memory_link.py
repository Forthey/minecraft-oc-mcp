from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, replace
from pathlib import Path

from adapter.parse import item_key

Pos = tuple[int, int, int]

HAZARD_BLOCKS = {
    "minecraft:lava": "lava",
    "minecraft:flowing_lava": "lava",
    "minecraft:fire": "fire",
    "minecraft:cactus": "cactus",
    "IC2:blockReactorChamber": "reactor",
    "IC2:blockGenerator": "machine",
}
DEFAULT_PROFILE = "adapter"


@dataclass(frozen=True)
class Zone:
    x: int
    y: int
    z: int
    radius: int
    label: str = ""

    def contains(self, p: Pos) -> bool:
        return max(abs(p[0] - self.x), abs(p[1] - self.y), abs(p[2] - self.z)) <= self.radius


@dataclass(frozen=True)
class Waypoint:
    x: int
    y: int
    z: int
    label: str = ""

    @property
    def pos(self) -> Pos:
        return (self.x, self.y, self.z)


def _dist(a: Pos, b: Pos) -> float:
    return math.hypot(a[0] - b[0], a[2] - b[2]) + 2.0 * abs(a[1] - b[1])


class MemoryLink:
    def __init__(self, world_id: str, robot_id: str = "robot", profile_id: str = DEFAULT_PROFILE,
                 db_path: Path | str | None = None, dim: int = 0, refresh_s: float = 30.0):
        self.world_id = world_id
        self.robot_id = robot_id
        self.profile_id = profile_id
        self.dim = dim
        self.refresh_s = refresh_s
        self.repo = None
        self.ctx_id: str | None = None
        self._zones: list[Zone] = []
        self._loaded_at = 0.0
        path = db_path or os.environ.get("MEMORY_DB")
        if not path:
            return
        try:
            from memory_mcp.config import load_settings
            from memory_mcp.repo import MemoryRepo
        except ImportError:
            return
        settings = replace(load_settings(), db_path=Path(path))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.repo = MemoryRepo(settings)

    @property
    def enabled(self) -> bool:
        return self.repo is not None

    def _ctx(self) -> str:
        if self.ctx_id is None:
            self.ctx_id = self.repo.open_context(self.world_id, self.profile_id, self.robot_id)["ctx_id"]
        return self.ctx_id

    def _rows(self, kind: str) -> list:
        now = int(time.time() * 1000)
        return self.repo.conn.execute(
            "SELECT x, y, z, radius, label FROM poi WHERE world_id = ? AND dim = ? AND kind = ? "
            "AND (ttl_at IS NULL OR ttl_at > ?) AND (scope = 'world' OR (scope = 'profile' AND owner = ?) "
            "OR (scope = 'robot' AND owner = ?))",
            (self.world_id, self.dim, kind, now, f"p:{self.profile_id}", f"r:{self.robot_id}"),
        ).fetchall()

    def hazards(self) -> list[Zone]:
        if not self.enabled:
            return []
        if time.monotonic() - self._loaded_at > self.refresh_s:
            self._zones = [Zone(r[0], r[1], r[2], r[3], r[4]) for r in self._rows("hazard")]
            self._loaded_at = time.monotonic()
        return self._zones

    def in_hazard(self, p: Pos) -> bool:
        return any(zone.contains(p) for zone in self.hazards())

    def waypoints(self) -> list[Waypoint]:
        if not self.enabled:
            return []
        return [Waypoint(r[0], r[1], r[2], r[4]) for r in self._rows("waypoint")]

    def route_hint(self, start: Pos, goal: Pos) -> list[Pos]:
        direct = _dist(start, goal)
        hops = []
        for wp in self.waypoints():
            p = wp.pos
            if _dist(start, p) < direct and _dist(p, goal) < direct:
                hops.append(p)
        hops.sort(key=lambda p: _dist(start, p))
        return hops

    def report_hazard(self, pos: Pos, block: str, radius: int = 1) -> dict | None:
        if not self.enabled or not 0 <= pos[1] <= 255:
            return None
        label = HAZARD_BLOCKS.get(item_key(block))
        if label is None:
            return None
        from memory_mcp.schemas import PoiRecord

        record = PoiRecord(kind="hazard", label=f"{label} ({item_key(block)})", dim=self.dim, x=pos[0], y=pos[1],
                           z=pos[2], radius=radius, tags=["auto", label], source="observed")
        result = self.repo.remember_poi(self._ctx(), record)
        self._loaded_at = 0.0
        return result

    def close(self) -> None:
        if self.repo is not None:
            self.repo.close()
