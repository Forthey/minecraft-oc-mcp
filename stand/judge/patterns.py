"""Шаблоны построек: повороты и кандидаты на размещение в мире."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from stand.world.blocks import Block, Pos


def _turn90(p: Pos) -> Pos:
    # Поворот на 90 градусов по часовой стрелке, если смотреть сверху: (x, z) в (-z, x).
    x, y, z = p
    return (-z, y, x)


def rotate(pattern: dict[Pos, Block], deg: int) -> dict[Pos, Block]:
    """Поворачивает шаблон вокруг Y и сдвигает так, чтобы минимальный угол был в (0, 0, 0)."""
    cells = dict(pattern)
    for _ in range((deg // 90) % 4):
        cells = {_turn90(p): b for p, b in cells.items()}
    if not cells:
        return {}
    mx = min(p[0] for p in cells)
    my = min(p[1] for p in cells)
    mz = min(p[2] for p in cells)
    return {(x - mx, y - my, z - mz): b for (x, y, z), b in cells.items()}


@dataclass(frozen=True)
class Placement:
    """Шаблон, поставленный в мир: минимальный угол origin, поворот и клетки мира."""

    origin: Pos
    rotation: int
    cells: tuple[tuple[Pos, Block], ...]

    @property
    def cell_map(self) -> dict[Pos, Block]:
        return dict(self.cells)


def place(pattern: dict[Pos, Block], rotation: int, origin: Pos) -> Placement:
    """Размещение повёрнутого шаблона с минимальным углом в origin."""
    rotated = rotate(pattern, rotation)
    ox, oy, oz = origin
    cells = tuple(sorted(((ox + x, oy + y, oz + z), b) for (x, y, z), b in rotated.items()))
    return Placement(origin, rotation, cells)


def candidates(
    pattern: dict[Pos, Block],
    rotations: list[int],
    changed: dict[Pos, Block],
) -> Iterator[Placement]:
    """Все размещения, при которых хотя бы одна клетка шаблона совпадает по имени
    блока с изменённой клеткой мира. Каждое размещение выдаётся один раз."""
    seen: set[tuple[Pos, int]] = set()
    for rot in rotations:
        rotated = rotate(pattern, rot)
        for p, actual in changed.items():
            for c, want in rotated.items():
                if want[0] != actual[0]:
                    continue
                origin = (p[0] - c[0], p[1] - c[1], p[2] - c[2])
                if (origin, rot) in seen:
                    continue
                seen.add((origin, rot))
                yield place(pattern, rot, origin)
