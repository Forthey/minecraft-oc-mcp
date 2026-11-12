from adapter.pathfinding import astar


def _free_except(blocked, bounds=10):
    def cost(p):
        if any(abs(v) > bounds for v in p) or p in blocked:
            return None
        return 1.0
    return cost


def test_straight_line():
    path = astar((0, 0, 0), (3, 0, 0), _free_except(set()))
    assert path == [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)]


def test_around_wall():
    wall = {(1, y, z) for y in range(-1, 2) for z in range(-1, 2)}
    path = astar((0, 0, 0), (2, 0, 0), _free_except(wall))
    assert path[0] == (0, 0, 0) and path[-1] == (2, 0, 0)
    assert not set(path) & wall
    assert len(path) - 1 == 6


def test_enclosed_returns_none():
    goal = (5, 0, 0)
    shell = {(5 + dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)} - {goal}
    assert astar((0, 0, 0), goal, _free_except(shell)) is None


def test_max_nodes_limit():
    assert astar((0, 0, 0), (9, 9, 9), _free_except(set()), max_nodes=5) is None


def test_prefers_cheap_cells():
    def cost(p):
        if any(abs(v) > 3 for v in p):
            return None
        return 5.0 if p == (1, 0, 0) else 1.0

    path = astar((0, 0, 0), (2, 0, 0), cost)
    assert (1, 0, 0) not in path
