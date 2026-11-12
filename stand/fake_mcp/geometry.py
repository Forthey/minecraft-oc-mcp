"""Направления и арифметика позиций мира для модели робота."""

from __future__ import annotations

from stand.world.blocks import Pos

# Стороны света по часовой стрелке: поворот направо это следующий элемент.
FACINGS = ("north", "east", "south", "west")
DIRS: dict[str, Pos] = {
    "north": (0, 0, -1),
    "south": (0, 0, 1),
    "east": (1, 0, 0),
    "west": (-1, 0, 0),
    "up": (0, 1, 0),
    "down": (0, -1, 0),
}


def add(a: Pos, b: Pos) -> Pos:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Pos, b: Pos) -> Pos:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(d: Pos, n: int) -> Pos:
    return (d[0] * n, d[1] * n, d[2] * n)
