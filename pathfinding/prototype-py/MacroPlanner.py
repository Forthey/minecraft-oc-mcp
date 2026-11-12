from RegionEstimater import RegionCostEstimator
from RegionCoord import RegionCoord
import math


MIN_COST_FACTOR = 0.5
# Конечная стоимость для «непроходимых» регионов:
# A* будет их избегать, но путь через них останется возможным.
# Это спасает, когда цель или старт оказались в таком регионе.
MAX_COST_FACTOR = 50.0


class MacroPlanner:
    def __init__(self, estimator: RegionCostEstimator, margin: int = 2):
        self.estimator = estimator
        self.margin = margin

    def plan(self, start_xyz, goal_xyz):
        s = RegionCoord.from_world(start_xyz[0], start_xyz[2])
        g = RegionCoord.from_world(goal_xyz[0], goal_xyz[2])
        if s == g:
            return [s]
        return self._astar(s, g)

    def _astar(self, start, goal):
        bounds = (
            min(start.x, goal.x) - self.margin,
            max(start.x, goal.x) + self.margin,
            min(start.z, goal.z) - self.margin,
            max(start.z, goal.z) + self.margin,
        )

        def heuristic(a, b):
            return (abs(a.x - b.x) + abs(a.z - b.z)) * 512 * MIN_COST_FACTOR

        def edge_weight(info):
            c = info.cost_factor
            if c == float("inf"):
                return 512 * MAX_COST_FACTOR
            return 512 * c

        open_set = {start}
        came_from = {}
        g_score = {start: 0.0}
        f_score = {start: heuristic(start, goal)}

        while open_set:
            current = min(open_set, key=lambda c: f_score.get(c, math.inf))
            if current == goal:
                return self._reconstruct(came_from, current)

            open_set.remove(current)
            for n in self._neighbors(current, bounds):
                tentative = g_score[current] + edge_weight(self.estimator.estimate(n))
                if tentative < g_score.get(n, math.inf):
                    came_from[n] = current
                    g_score[n] = tentative
                    f_score[n] = tentative + heuristic(n, goal)
                    open_set.add(n)

        raise RuntimeError("No path found between regions")

    @staticmethod
    def _neighbors(c, bounds):
        min_x, max_x, min_z, max_z = bounds
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, nz = c.x + dx, c.z + dz
            if min_x <= nx <= max_x and min_z <= nz <= max_z:
                yield RegionCoord(nx, nz)

    @staticmethod
    def _reconstruct(came_from, current):
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path