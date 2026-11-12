from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Protocol

from adapter.parse import item_key
from adapter.pose import DIRS, Pose

Pos = tuple[int, int, int]

SOLID, AIR, LIQUID = "solid", "air", "liquid"
LIQUID_HARDNESS = 100.0
AIR_KINDS = {"air", "passable", "replaceable", "entity"}
AXES_RE = re.compile(r"^axes: x = (\w+), z = (\w+), y = up$")
LAYER_RE = re.compile(r"^y=(-?\d+) \(rows z=(-?\d+)\.\.(-?\d+), columns x=(-?\d+)\.\.(-?\d+)\):$")
SIDE_RE = re.compile(r"^(front|back|left|right|up|down):\s*(.*)$")
NAME_RE = re.compile(r"^([A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-/]+(?::\d+)?)")
KIND_RE = re.compile(r"\((\w+)\)")
MOVE_SIDES = {"forward": "front", "back": "back", "up": "up", "down": "down"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS cells (
  world_id TEXT NOT NULL,
  x INTEGER NOT NULL, y INTEGER NOT NULL, z INTEGER NOT NULL,
  state TEXT NOT NULL,
  name TEXT,
  source TEXT NOT NULL,
  updated_at REAL NOT NULL,
  PRIMARY KEY (world_id, x, y, z)
)
"""


class HazardSource(Protocol):
    def in_hazard(self, p: Pos) -> bool: ...


class Cell:
    __slots__ = ("state", "name", "source", "updated_at")

    def __init__(self, state: str, name: str | None, source: str, updated_at: float):
        self.state = state
        self.name = name
        self.source = source
        self.updated_at = updated_at


def _add(a: Pos, b: Pos, n: int = 1) -> Pos:
    return (a[0] + b[0] * n, a[1] + b[1] * n, a[2] + b[2] * n)


class ExploredMap:
    available = True

    def __init__(self, world_id: str = "default", db_path: Path | str | None = None, radius: int | None = None,
                 hazards: HazardSource | None = None):
        self.world_id = world_id
        self.db_path = Path(db_path) if db_path else None
        self.radius = radius
        self.hazards = hazards
        self.cells: dict[Pos, Cell] = {}
        self._dirty: set[Pos] = set()
        self.last_unverified: list[dict] = []
        self._box: tuple[Pos, Pos] | None = None
        if self.db_path is not None:
            self.load()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute(SCHEMA)
        return conn

    def load(self) -> None:
        if self.db_path is None or not self.db_path.exists():
            return
        with self._connect() as conn:
            rows = conn.execute("SELECT x, y, z, state, name, source, updated_at FROM cells WHERE world_id = ?",
                                (self.world_id,)).fetchall()
        for x, y, z, state, name, source, updated in rows:
            self.cells[(x, y, z)] = Cell(state, name, source, updated)

    def flush(self) -> None:
        if self.db_path is None or not self._dirty:
            return
        rows = [(self.world_id, *p, c.state, c.name, c.source, c.updated_at)
                for p in self._dirty if (c := self.cells.get(p))]
        with self._connect() as conn:
            conn.executemany("INSERT OR REPLACE INTO cells VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        self._dirty.clear()

    def mark(self, pos: Pos, state: str, name: str | None = None, source: str = "observed") -> None:
        pos = tuple(int(v) for v in pos)
        old = self.cells.get(pos)
        if name is None and old is not None and old.state == state and source == "geo_scan":
            name = old.name
        if old is None:
            self._box = None
        self.cells[pos] = Cell(state, name, source, time.time())
        self._dirty.add(pos)

    def get(self, pos: Pos) -> Cell | None:
        return self.cells.get(tuple(pos))

    def region_contains(self, p: Pos) -> bool:
        if self.radius is None:
            return True
        if not self.cells:
            return False
        lo, hi = self._bounds()
        return all(lo[i] - self.radius <= p[i] <= hi[i] + self.radius for i in range(3))

    def _bounds(self) -> tuple[Pos, Pos]:
        if self._box is None:
            cells = list(self.cells)
            self._box = (tuple(min(c[i] for c in cells) for i in range(3)),
                         tuple(max(c[i] for c in cells) for i in range(3)))
        return self._box

    def occupied(self, p: Pos) -> bool:
        if self.hazards is not None and self.hazards.in_hazard(tuple(p)):
            return True
        cell = self.cells.get(tuple(p))
        return cell is not None and cell.state != AIR

    def invalidate(self) -> None:
        pass

    def verify(self, expected: list[dict]) -> tuple[list[dict], list[dict]]:
        missing, wrong, unverified = [], [], []
        for entry in expected:
            pos = tuple(entry["pos"])
            cell = self.cells.get(pos)
            item = {"pos": list(pos), "item": entry["item"]}
            if cell is None or cell.state == AIR:
                missing.append(item)
            elif cell.name is None:
                unverified.append(item)
            elif item_key(cell.name) != item_key(entry["item"]):
                wrong.append({**item, "found": cell.name})
        self.last_unverified = unverified
        return missing, wrong

    def ingest_geo_scan(self, pose: Pose, args: dict, text: str) -> int:
        count = 0
        for world, value in geo_cells(pose, text):
            if world == pose.pos:
                continue
            self.mark(world, geo_state(value), source="geo_scan")
            count += 1
        return count


    def ingest_surroundings(self, pose: Pose, text: str) -> list[tuple[Pos, str, str | None]]:
        seen = []
        if not pose.known:
            return seen
        for line in text.splitlines():
            m = SIDE_RE.match(line.strip())
            if not m:
                continue
            target = pose.side_pos(m.group(1))
            if target is None:
                continue
            rest = m.group(2)
            name_m = NAME_RE.match(rest)
            name = name_m.group(1) if name_m else None
            kind_m = KIND_RE.search(rest)
            kind = kind_m.group(1) if kind_m else None
            if name and item_key(name) == "minecraft:air":
                state, name = AIR, None
            elif kind in AIR_KINDS and not name:
                state = AIR
            elif kind == "liquid":
                state = LIQUID
            elif kind in AIR_KINDS:
                state = AIR
            elif name or kind == "solid":
                state = SOLID
            else:
                continue
            self.mark(target, state, name, source="surroundings")
            seen.append((target, state, name))
        return seen

    def on_moved(self, pose: Pose) -> None:
        if pose.pos is not None:
            self.mark(pose.pos, AIR, source="move")

    def on_move_blocked(self, pose: Pose, direction: str) -> None:
        target = pose.side_pos(MOVE_SIDES.get(direction, direction))
        if target is not None:
            self.mark(target, SOLID, source="move")

    def on_place(self, pose: Pose, side: str, item: str | None = None) -> None:
        target = pose.side_pos(side)
        if target is not None:
            self.mark(target, SOLID, item, source="place")

    def on_swing(self, pose: Pose, side: str) -> None:
        target = pose.side_pos(side)
        if target is not None:
            self.mark(target, AIR, source="swing")


def geo_axes(pose: Pose, relative: bool) -> tuple[Pos, Pos] | None:
    if not relative:
        return DIRS["east"], DIRS["south"]
    if pose.facing is None:
        return None
    return pose.side_dir("right"), pose.side_dir("front")


def geo_cells(pose: Pose, text: str) -> list[tuple[Pos, float]]:
    out: list[tuple[Pos, float]] = []
    if pose.pos is None:
        return out
    lines = [line.strip() for line in text.splitlines()]
    if not lines:
        return out
    m = AXES_RE.match(lines[0])
    axes = geo_axes(pose, bool(m) and m.group(1) == "right")
    if axes is None:
        return out
    right, forward = axes
    i = 1
    while i < len(lines):
        layer = LAYER_RE.match(lines[i])
        i += 1
        if not layer:
            continue
        y, z0, z1, x0 = (int(layer.group(k)) for k in (1, 2, 3, 4))
        for dz in range(z1 - z0 + 1):
            if i >= len(lines):
                break
            for dx, token in enumerate(lines[i].split()):
                value = geo_value(token)
                if value is None:
                    continue
                a, b = x0 + dx, z0 + dz
                world = (pose.pos[0] + a * right[0] + b * forward[0], pose.pos[1] + y,
                         pose.pos[2] + a * right[2] + b * forward[2])
                out.append((world, value))
            i += 1
    return out


def geo_value(token: str) -> float | None:
    if token == "?":
        return None
    if token == ".":
        return 0.0
    try:
        return float(token)
    except ValueError:
        return None


def geo_state(value: float) -> str:
    if value == 0:
        return AIR
    return LIQUID if value >= LIQUID_HARDNESS else SOLID
