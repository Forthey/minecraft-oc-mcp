from adapter.pose import Pose


def test_sync_from_world_info():
    p = Pose()
    assert not p.known
    assert p.sync({"x": 100, "y": 64, "z": 105, "facing": "north"})
    assert p.known and p.pos == (100, 64, 105) and p.facing == "north"
    assert not Pose().sync({"position_error": "no navigation upgrade: position unknown"})


def test_turns():
    p = Pose((0, 0, 0), "north")
    p.apply_turn("right")
    assert p.facing == "east"
    p.apply_turn("around")
    assert p.facing == "west"
    p.apply_turn("left")
    assert p.facing == "south"


def test_moves_and_sides():
    p = Pose((0, 64, 0), "east")
    assert p.side_pos("front") == (1, 64, 0) and p.side_pos("left") == (0, 64, -1)
    assert p.side_pos("up") == (0, 65, 0) and p.side_pos("back") == (-1, 64, 0)
    p.apply_move("forward", 2)
    assert p.pos == (2, 64, 0)
    p.apply_move("up", 1)
    p.apply_move("back", 1)
    assert p.pos == (1, 65, 0)
    assert p.dir_to("south") == (0, 0, 1) and p.dir_to("down") == (0, -1, 0)


def test_turn_needed():
    p = Pose((0, 0, 0), "north")
    assert p.turn_to("north") is None and p.turn_to("east") == "right"
    assert p.turn_to("west") == "left" and p.turn_to("south") == "around"
