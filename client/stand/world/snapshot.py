"""Снимок региона мира: какие блоки отличаются от чистого плоского мира.

Судья и сброс региона работают только со снимком, поэтому он не зависит от MCP.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from stand.rcon import Rcon
from stand.world.anvil import chunk_sections, read_chunk, section_block
from stand.world.blocks import AIR, Block, Pos, baseline_block
from stand.world.nbt import NbtError
from stand.world.registry import load_block_registry


@dataclass(frozen=True)
class Box:
    """Прямоугольная область, обе границы включительно. Углы нормализуются."""

    lo: Pos
    hi: Pos

    def __post_init__(self):
        lo = tuple(min(a, b) for a, b in zip(self.lo, self.hi))
        hi = tuple(max(a, b) for a, b in zip(self.lo, self.hi))
        object.__setattr__(self, "lo", lo)
        object.__setattr__(self, "hi", hi)

    def contains(self, p: Pos) -> bool:
        return all(lo <= v <= hi for v, lo, hi in zip(p, self.lo, self.hi))

    def iter(self) -> Iterator[Pos]:
        (x0, y0, z0), (x1, y1, z1) = self.lo, self.hi
        for y in range(y0, y1 + 1):
            for z in range(z0, z1 + 1):
                for x in range(x0, x1 + 1):
                    yield (x, y, z)

    def to_json(self) -> dict:
        return {"from": list(self.lo), "to": list(self.hi)}

    @classmethod
    def from_json(cls, d: dict) -> "Box":
        return cls(tuple(d["from"]), tuple(d["to"]))


@dataclass
class Snapshot:
    """Состояние региона. Хранит только клетки, отличные от baseline_block."""

    box: Box
    blocks: dict[Pos, Block] = field(default_factory=dict)

    def get(self, p: Pos) -> Block:
        """Блок в позиции. Для клеток без записи возвращает базовый блок."""
        return self.blocks.get(p, baseline_block(p[1]))

    def changed(self) -> dict[Pos, Block]:
        """Клетки, которые отличаются от чистого мира."""
        return dict(self.blocks)

    def to_json(self) -> dict:
        return {
            "box": self.box.to_json(),
            "blocks": [[*p, name, meta] for p, (name, meta) in sorted(self.blocks.items())],
        }

    @classmethod
    def from_json(cls, d: dict) -> "Snapshot":
        blocks = {(x, y, z): (name, meta) for x, y, z, name, meta in d["blocks"]}
        return cls(Box.from_json(d["box"]), blocks)


def read_snapshot(world_dir: Path, box: Box) -> Snapshot:
    """Читает регион из region-файлов. Несгенерированный чанк считается чистым миром."""
    registry = load_block_registry(world_dir / "level.dat")
    region_dir = world_dir / "region"
    (x0, y0, z0), (x1, y1, z1) = box.lo, box.hi
    blocks: dict[Pos, Block] = {}
    for cx in range(x0 >> 4, (x1 >> 4) + 1):
        for cz in range(z0 >> 4, (z1 >> 4) + 1):
            chunk = read_chunk(region_dir, cx, cz)
            if chunk is None:
                continue
            sections = chunk_sections(chunk)
            for x in range(max(x0, cx * 16), min(x1, cx * 16 + 15) + 1):
                for z in range(max(z0, cz * 16), min(z1, cz * 16 + 15) + 1):
                    for y in range(y0, y1 + 1):
                        section = sections.get(y >> 4)
                        if section is None:
                            block = AIR
                        else:
                            block_id, meta = section_block(section, x & 15, y & 15, z & 15)
                            name = registry.get(block_id, f"unknown:{block_id}")
                            block = (name, 0) if name == AIR[0] else (name, meta)
                        if block != baseline_block(y):
                            blocks[(x, y, z)] = block
    return Snapshot(box, blocks)


def capture(
    rcon: Rcon,
    world_dir: Path,
    box: Box,
    settle: float = 0.5,
    attempts: int = 8,
) -> Snapshot:
    """Сохраняет мир через save-all и читает снимок региона.

    В 1.7.10 save-all ставит чанки в очередь записи, а пишет их отдельный поток.
    Поэтому снимок читается повторно, пока два чтения подряд не совпадут. Чтение
    полузаписанного файла тоже просто повторяется.
    """
    rcon.command("save-all")
    previous = None
    for _ in range(attempts):
        time.sleep(settle)
        try:
            snap = read_snapshot(world_dir, box)
        except (NbtError, OSError, ValueError, KeyError):
            continue
        if previous is not None and snap.blocks == previous.blocks:
            return snap
        previous = snap
    if previous is None:
        raise RuntimeError(f"cannot read world snapshot from {world_dir}")
    return previous
