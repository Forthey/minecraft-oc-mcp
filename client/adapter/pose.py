"""Позиция и направление робота, которые адаптер ведёт сам.

oc-mcp отдаёт координаты только через world_info (нужен Navigation Upgrade), а move и
turn относительны. Поэтому адаптер берёт позицию из world_info и дальше учитывает свои
ходы и повороты. После ошибок связи позиция пересинхронизируется через world_info.
"""

from __future__ import annotations

Pos = tuple[int, int, int]

FACINGS = ("north", "east", "south", "west")
DIRS: dict[str, Pos] = {
    "north": (0, 0, -1),
    "south": (0, 0, 1),
    "east": (1, 0, 0),
    "west": (-1, 0, 0),
    "up": (0, 1, 0),
    "down": (0, -1, 0),
}
TURNS = {"right": 1, "around": 2, "left": 3}
SIDE_TURNS = {"front": 0, "right": 1, "back": 2, "left": 3}


def _add(a: Pos, b: Pos, n: int = 1) -> Pos:
    return (a[0] + b[0] * n, a[1] + b[1] * n, a[2] + b[2] * n)


class Pose:
    """pos и facing робота. None, пока позиция неизвестна."""

    def __init__(self, pos: Pos | None = None, facing: str | None = None):
        self.pos = tuple(pos) if pos is not None else None
        self.facing = facing

    @property
    def known(self) -> bool:
        return self.pos is not None and self.facing in FACINGS

    def sync(self, info: dict) -> bool:
        """Берёт позицию из ответа world_info. False, если в нём нет координат или направления."""
        if all(k in info for k in ("x", "y", "z")) and info.get("facing") in FACINGS:
            self.pos = (int(info["x"]), int(info["y"]), int(info["z"]))
            self.facing = info["facing"]
            return True
        return False

    def dir_to(self, direction: str) -> Pos:
        """Вектор стороны света или up и down."""
        return DIRS[direction]

    def side_dir(self, side: str) -> Pos | None:
        """Вектор стороны робота: front, back, left, right, up, down."""
        if side in ("up", "down"):
            return DIRS[side]
        turn = SIDE_TURNS.get(side)
        if turn is None or self.facing not in FACINGS:
            return None
        return DIRS[FACINGS[(FACINGS.index(self.facing) + turn) % 4]]

    def side_pos(self, side: str) -> Pos | None:
        """Клетка на стороне робота."""
        d = self.side_dir(side)
        return None if d is None or self.pos is None else _add(self.pos, d)

    def apply_turn(self, direction: str) -> None:
        self.facing = FACINGS[(FACINGS.index(self.facing) + TURNS[direction]) % 4]

    def apply_move(self, direction: str, k: int) -> None:
        """Сдвигает позицию на k шагов move (forward, back, up, down)."""
        side = {"forward": "front", "back": "back", "up": "up", "down": "down"}[direction]
        self.pos = _add(self.pos, self.side_dir(side), k)

    def turn_to(self, direction: str) -> str | None:
        """Какой turn нужен, чтобы смотреть на direction. None, если уже смотрит."""
        diff = (FACINGS.index(direction) - FACINGS.index(self.facing)) % 4
        return {0: None, 1: "right", 2: "around", 3: "left"}[diff]
