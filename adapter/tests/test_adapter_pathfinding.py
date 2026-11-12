from adapter.pathfinding import NEIGHBOURS, astar


def test_stand_reexports_adapter_astar():
    import stand.fake_mcp.pathfinding as stand_pf

    assert stand_pf.astar is astar and stand_pf.NEIGHBOURS is NEIGHBOURS


def test_straight_line():
    path = astar((0, 0, 0), (3, 0, 0), lambda p: 1.0)
    assert path == [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)]
