from adapter.pathfinding import astar


def test_straight_line():
    path = astar((0, 0, 0), (3, 0, 0), lambda p: 1.0)
    assert path == [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)]
