import json

import anyio

from adapter.pose import label_coords, waypoint_pos
from adapter.robot import RobotAdapter
from adapter.worldmap import NoMap
from adapter_harness import bridge, make_sim
from test_adapter_pose_sync import StubUpstream


def test_label_coords_formats():
    assert label_coords("0 64 0") == (0, 64, 0)
    assert label_coords("0,64,-5") == (0, 64, -5)
    assert label_coords("base 12 70 -300") == (12, 70, -300)
    assert label_coords("base") is None


def test_waypoint_pos_skips_unlabeled():
    wps = [{"label": "home", "dx": 1, "dy": 0, "dz": 0}, {"label": "10 64 20", "dx": 3, "dy": -1, "dz": -2}]
    assert waypoint_pos(wps) == (7, 65, 22)


def test_waypoint_calibration_then_move(tmp_path):
    sim = make_sim()
    start = tuple(sim.pos)
    mark = (start[0] + 3, start[1], start[2] - 2)

    async def go():
        async with bridge(sim, tmp_path, waypoints=[("depot %d %d %d" % mark, mark)]) as up:
            ad = RobotAdapter(up, NoMap())
            status = await ad.call("get_status", {})
            assert status["ok"], status
            assert status["data"]["pos"] == list(start)
            assert status["data"]["pose_source"] == "waypoint"
            moved = await ad.call("move", {"direction": "up", "n": 1})
            assert moved["ok"], moved
            assert moved["data"]["pos"] == [start[0], start[1] + 1, start[2]]
            again = await ad.call("get_status", {})
            assert again["data"]["pos"] == [start[0], start[1] + 1, start[2]]

    anyio.run(go)


def test_navigation_wins_over_waypoint():
    info = {"robot_id": "r", "x": 1, "y": 2, "z": 3, "facing": "east",
            "waypoints": [{"label": "100 100 100", "dx": 0, "dy": 0, "dz": 0}]}
    ad = RobotAdapter(StubUpstream({"world_info": (True, json.dumps(info))}))
    anyio.run(ad.sync)
    assert ad.pose.pos == (1, 2, 3) and ad.pose.source == "navigation"


def test_unlabeled_waypoint_gives_hint():
    info = {"robot_id": "r", "facing": "north", "position_error": "navigation upgrade: out of range",
            "waypoints": [{"label": "home", "dx": 1, "dy": 0, "dz": 0}]}
    ad = RobotAdapter(StubUpstream({"world_info": (True, json.dumps(info))}))
    env = anyio.run(ad.call, "face", {"direction": "east"})
    assert env["error_code"] == "UNSUPPORTED"
    assert env["message"].startswith("robot position unknown: navigation upgrade: out of range. Place an "
                                     "OpenComputers Waypoint within 400 blocks")
