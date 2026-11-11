"""Поиск пути A* по сетке блоков с шестью соседями."""

from __future__ import annotations

import heapq
from itertools import count
from typing import Callable

Pos = tuple[int, int, int]

NEIGHBOURS: tuple[Pos, ...] = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def _h(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


def astar(
    start: Pos,
    goal: Pos,
    cost: Callable[[Pos], float | None],
    max_nodes: int = 20000,
) -> list[Pos] | None:
    """Путь от start до goal включительно или None.

    cost(p) это цена входа в клетку, None значит непроходимо. Стартовая клетка не
    оценивается. Эвристика Манхэттен допустима, пока цена клетки не меньше 1.
    max_nodes ограничивает число раскрытых клеток.
    """
    if start == goal:
        return [start]
    tie = count()
    open_heap = [(_h(start, goal), next(tie), start)]
    g = {start: 0.0}
    parent: dict[Pos, Pos] = {}
    closed: set[Pos] = set()
    while open_heap:
        _, _, cur = heapq.heappop(open_heap)
        if cur in closed:
            continue
        if cur == goal:
            path = [cur]
            while cur in parent:
                cur = parent[cur]
                path.append(cur)
            return path[::-1]
        closed.add(cur)
        if len(closed) > max_nodes:
            return None
        for d in NEIGHBOURS:
            nxt = (cur[0] + d[0], cur[1] + d[1], cur[2] + d[2])
            if nxt in closed:
                continue
            c = cost(nxt)
            if c is None:
                continue
            ng = g[cur] + c
            if ng < g.get(nxt, float("inf")):
                g[nxt] = ng
                parent[nxt] = cur
                heapq.heappush(open_heap, (ng + _h(nxt, goal), next(tie), nxt))
    return None
