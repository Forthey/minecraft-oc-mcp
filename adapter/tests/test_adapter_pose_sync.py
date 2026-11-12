"""Позиция робота без моста: заглушка upstream с заданными ответами (таймаут моста ждать 30 с)."""

import json
from pathlib import Path

import anyio

from adapter.__main__ import build_bridge_cmd, main_parser
from adapter.robot import RobotAdapter

NAV = json.dumps({"robot_id": "r", "x": 100, "y": 64, "z": 105, "facing": "north"})
NO_NAV = json.dumps({"robot_id": "r", "position_error": "no navigation upgrade: position unknown"})
TIMEOUT = "OpenComputers did not respond within 30s. The command may still run later."


class StubUpstream:
    """upstream.call по таблице ответов. Значение может быть списком: ответы по очереди."""

    def __init__(self, answers: dict):
        self.answers = {k: (list(v) if isinstance(v, list) else v) for k, v in answers.items()}
        self.calls: list[str] = []

    async def call(self, name, args):
        self.calls.append(name)
        a = self.answers[name]
        return a.pop(0) if isinstance(a, list) else a


def test_pose_synced_lazily_on_first_addition():
    up = StubUpstream({"world_info": (True, NAV), "turn": (True, "Turned right.")})
    ad = RobotAdapter(up)  # start() не вызывался, как в CLI, который сразу отвечает на initialize
    env = anyio.run(ad.call, "face", {"direction": "east"})
    assert env["ok"] and ad.pose.facing == "east"
    assert up.calls == ["world_info", "turn"]


def test_silent_robot_is_not_reported_as_missing_navigation():
    up = StubUpstream({"world_info": (False, TIMEOUT)})
    env = anyio.run(RobotAdapter(up).call, "face", {"direction": "east"})
    assert env["error_code"] == "CONNECTION_LOST"
    assert env["message"] == "robot does not respond: position unknown"


def test_missing_navigation_is_unsupported():
    up = StubUpstream({"world_info": (True, NO_NAV)})
    env = anyio.run(RobotAdapter(up).call, "face", {"direction": "east"})
    assert env["error_code"] == "UNSUPPORTED"
    assert env["message"] == "robot position unknown: navigation upgrade required"


def test_failed_resync_marks_pose_unknown():
    up = StubUpstream({"world_info": [(True, NAV), (False, TIMEOUT)], "move": (False, TIMEOUT)})
    ad = RobotAdapter(up)

    async def go():
        await ad.start()
        assert ad.pose.known
        return await ad.call("move", {"direction": "forward", "n": 1})

    env = anyio.run(go)
    assert env["error_code"] == "CONNECTION_LOST" and not ad.pose.known


def test_bridge_log_defaults_outside_oc_mcp():
    args = main_parser().parse_args(["--oc-mcp", "/x/oc-mcp/bridge/server.py", "--port", "9001"])
    cmd = build_bridge_cmd(args)
    log = Path(cmd[cmd.index("--log-file") + 1])
    assert "/x/oc-mcp" not in str(log) and log.name == "oc-mcp-bridge-9001.log"
