"""Сквозные tools oc-mcp через RobotAdapter: коды ошибок, data, pose и журнал."""

import json

import anyio
from adapter_harness import bridge, make_sim

from adapter.action_log import ActionLog
from adapter.robot import RobotAdapter
from adapter.worldmap import NoMap

STONE = ("minecraft:stone", 0)


def _run(sim, tmp_path, script, **double_kwargs):
    """Запускает мост и адаптер, выполняет script(adapter) и возвращает (результат, адаптер)."""
    async def go():
        async with bridge(sim, tmp_path, **double_kwargs) as up:
            ad = RobotAdapter(up, NoMap(), ActionLog(tmp_path / "action_log.jsonl"))
            await ad.start()
            return await script(ad), ad

    return anyio.run(go)


def test_place_gets_target_pos(tmp_path):
    sim = make_sim(pos=(100, 64, 105), facing="north", inventory=[{"item": "minecraft:cobblestone", "count": 9}])

    async def script(ad):
        return await ad.call("place", {"side": "front", "slot": 1})

    env, _ = _run(sim, tmp_path, script)
    assert env["ok"] and env["data"]["pos"] == [100, 64, 104]
    assert env["message"] == "Placed from slot 1 front: minecraft:cobblestone. 8 left in slot 1."


def test_partial_move_shifts_pose_by_k(tmp_path):
    sim = make_sim(pos=(100, 64, 105), facing="north", setup={(100, 64, 102): STONE})

    async def script(ad):
        return await ad.call("move", {"direction": "forward", "n": 3})

    env, ad = _run(sim, tmp_path, script)
    assert env["ok"] is False and env["error_code"] == "BLOCKED"
    assert env["message"] == "moved 2 of 3 blocks forward, blocked: solid"
    assert ad.pose.pos == (100, 64, 103) == sim.pos
    assert env["data"]["pos"] == [100, 64, 103]


def test_turn_updates_facing(tmp_path):
    async def script(ad):
        return await ad.call("turn", {"direction": "right"})

    env, ad = _run(make_sim(facing="north"), tmp_path, script)
    assert env["ok"] and ad.pose.facing == "east" and env["data"]["facing"] == "east"


def test_scans_get_slots(tmp_path):
    sim = make_sim(pos=(96, 64, 105), facing="west", inventory=[{"item": "minecraft:cobblestone", "count": 9}])

    async def script(ad):
        return await ad.call("inventory_scan", {}), await ad.call("storage_scan", {"side": "front"})

    (inv, st), _ = _run(sim, tmp_path, script)
    assert inv["data"]["slots"] == [{"slot": 1, "count": 9, "name": "minecraft:cobblestone:0", "label": "Cobblestone"}]
    assert st["data"]["block"] == "minecraft:chest" and st["data"]["size"] == 27


def test_world_info_and_nei_json(tmp_path):
    async def script(ad):
        return await ad.call("world_info", {}), await ad.call("nei_find", {"text": "chest"})

    (wi, nf), _ = _run(make_sim(), tmp_path, script)
    assert wi["data"]["x"] == 100 and nf["data"]["items"]


def test_bad_argument_is_blocked(tmp_path):
    async def script(ad):
        return await ad.call("move", {})

    env, _ = _run(make_sim(), tmp_path, script)
    assert env == {"ok": False, "error_code": "BLOCKED", "message": "bad argument: direction is required", "data": {}}


def test_unsupported_tool(tmp_path):
    async def script(ad):
        return await ad.call("geo_scan", {})

    env, _ = _run(make_sim(), tmp_path, script, disabled={"geo_scan": "missing component: geolyzer"})
    assert env["error_code"] == "UNSUPPORTED"


def test_call_logs_raw_does_not(tmp_path):
    async def script(ad):
        await ad.call("turn", {"direction": "left"})
        await ad.raw("turn", {"direction": "left"})
        return await ad.call("get_action_log", {"last_n": 10})

    env, ad = _run(make_sim(), tmp_path, script)
    assert [a["tool"] for a in env["data"]["actions"]] == ["turn"]
    lines = (tmp_path / "action_log.jsonl").read_text().splitlines()
    assert [json.loads(line)["tool"] for line in lines] == ["turn", "get_action_log"]
    assert set(json.loads(lines[0])) == {"ts", "tool", "args", "ok", "error_code", "duration_ms", "fault", "data"}
