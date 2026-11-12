"""Добавки адаптера поверх настоящего моста oc-mcp и тестового робота, карта по миру в памяти."""

import anyio
from adapter_harness import bridge, make_sim

from adapter.action_log import ActionLog
from adapter.robot import RobotAdapter
from adapter.worldmap import NoMap
from stand.adapter_map import SnapshotMap, memory_snapshot

STONE = ("minecraft:stone", 0)
COBBLE = ("minecraft:cobblestone", 0)


def _map(sim):
    return SnapshotMap(sim.region, sim.k, lambda: memory_snapshot(sim.world, sim.region), sim.world)


def _run(sim, tmp_path, script, with_map=True, **double_kwargs):
    async def go():
        async with bridge(sim, tmp_path, **double_kwargs) as up:
            ad = RobotAdapter(up, _map(sim) if with_map else NoMap(), ActionLog(tmp_path / "action_log.jsonl"))
            await ad.start()
            return await script(ad), ad

    return anyio.run(go)


def test_face_turns_once(tmp_path):
    async def script(ad):
        return await ad.call("face", {"direction": "west"})

    env, ad = _run(make_sim(facing="north"), tmp_path, script)
    assert env["ok"] and env["data"] == {"facing": "west"} and ad.pose.facing == "west"


def test_move_to_reaches_target_in_segments(tmp_path):
    sim = make_sim()

    async def script(ad):
        return await ad.call("move_to", {"x": 103, "y": 65, "z": 102})

    env, ad = _run(sim, tmp_path, script)
    assert env["ok"], env
    assert env["data"]["pos"] == [103, 65, 102] and sim.pos == (103, 65, 102) == ad.pose.pos
    assert env["data"]["steps"] == 3 + 1 + 3
    assert [e["tool"] for e in ad.log.entries] == ["move_to"]


def test_move_to_replans_on_unmapped_obstacle(tmp_path):
    sim = make_sim()
    world_map = _map(sim)

    async def script(ad):
        world_map.occupied((100, 64, 105))  # карта закэширована до появления камня
        sim.occ[(100, 64, 103)] = STONE
        sim.world.set_block((100, 64, 103), STONE)
        return await ad.call("move_to", {"x": 100, "y": 64, "z": 101})

    async def go():
        async with bridge(sim, tmp_path) as up:
            ad = RobotAdapter(up, world_map, ActionLog(None))
            await ad.start()
            return await script(ad)

    env = anyio.run(go)
    assert env["ok"], env
    assert sim.pos == (100, 64, 101)


def test_move_to_gives_up_after_two_replans(tmp_path):
    sim = make_sim()

    async def script(ad):
        sim.occ[(100, 64, 103)] = STONE  # робот упирается, а карта о камне не знает никогда
        return await ad.call("move_to", {"x": 100, "y": 64, "z": 101})

    env, _ = _run(sim, tmp_path, script)
    assert env["error_code"] == "BLOCKED" and env["message"].startswith("moved ")


def test_place_at_builds_block(tmp_path):
    sim = make_sim(inventory=[{"item": "minecraft:cobblestone", "count": 9}])

    async def script(ad):
        return await ad.call("place_at", {"x": 100, "y": 64, "z": 100, "item": "minecraft:cobblestone"})

    env, ad = _run(sim, tmp_path, script)
    assert env["ok"], env
    assert env["data"]["pos"] == [100, 64, 100] and env["data"]["slot"] == 1
    assert sim.world.get((100, 64, 100)) == COBBLE
    assert [e["tool"] for e in ad.log.entries] == ["place_at"]


def test_place_at_missing_item_and_occupied(tmp_path):
    sim = make_sim(inventory=[{"item": "minecraft:cobblestone", "count": 9}], setup={(101, 64, 100): STONE})

    async def script(ad):
        return (await ad.call("place_at", {"x": 100, "y": 64, "z": 100, "item": "minecraft:planks"}),
                await ad.call("place_at", {"x": 101, "y": 64, "z": 100, "item": "minecraft:cobblestone"}),
                await ad.call("place_at", {"x": 100, "y": 64, "z": 100, "item": "not an id"}),
                await ad.call("place_at", {"x": 500, "y": 64, "z": 100, "item": "minecraft:cobblestone"}))

    (missing, occupied, bad, far), _ = _run(sim, tmp_path, script)
    assert missing["error_code"] == "NO_ITEM"
    assert occupied["error_code"] == "CANT_PLACE"
    assert bad["error_code"] == "UNKNOWN_ITEM"
    assert far["error_code"] == "OUT_OF_RANGE"


def test_verify_blocks_missing_wrong(tmp_path):
    sim = make_sim(setup={(100, 64, 100): STONE})

    async def script(ad):
        return await ad.call("verify_blocks", {"expected": [
            {"pos": [100, 64, 100], "item": "minecraft:cobblestone"},
            {"pos": [101, 64, 100], "item": "minecraft:cobblestone"}]})

    env, _ = _run(sim, tmp_path, script)
    assert env["data"]["wrong"] == [{"pos": [100, 64, 100], "item": "minecraft:cobblestone:0"}]
    assert env["data"]["missing"] == [{"pos": [101, 64, 100], "item": "minecraft:cobblestone:0"}]
    assert env["data"]["checked"] == 2 and env["data"]["next_page"] is None


def test_without_navigation_unsupported(tmp_path):
    async def script(ad):
        return (await ad.call("move_to", {"x": 100, "y": 64, "z": 101}),
                await ad.call("place_at", {"x": 100, "y": 64, "z": 100, "item": "minecraft:cobblestone"}),
                await ad.call("inventory_scan", {}))

    (mv, pl, inv), _ = _run(make_sim(), tmp_path, script, navigation=False)
    for env in (mv, pl):
        assert env["error_code"] == "UNSUPPORTED"
        assert env["message"] == "robot position unknown: navigation upgrade required"
    assert inv["ok"]


def test_without_map_unsupported(tmp_path):
    async def script(ad):
        return await ad.call("verify_blocks", {"expected": []})

    env, _ = _run(make_sim(), tmp_path, script, with_map=False)
    assert env["error_code"] == "UNSUPPORTED" and env["message"] == "no world map"


def test_search_docs_unsupported(tmp_path):
    async def script(ad):
        return await ad.call("search_docs", {"query": "reactor"})

    env, _ = _run(make_sim(), tmp_path, script)
    assert env["error_code"] == "UNSUPPORTED" and env["message"] == "no documentation service"


def test_get_status_shape(tmp_path):
    sim = make_sim(inventory=[{"item": "minecraft:cobblestone", "count": 9}])

    async def script(ad):
        return await ad.call("get_status", {})

    env, _ = _run(sim, tmp_path, script)
    assert env["data"] == {"pos": [100, 64, 105], "facing": "north",
                           "inventory": [{"slot": 1, "count": 9, "name": "minecraft:cobblestone:0"}]}


def test_concurrent_calls_do_not_corrupt_pose(tmp_path):
    """Агент может слать tools параллельно: вызовы адаптера идут строго по одному."""
    sim = make_sim()
    results = {}

    async def script(ad):
        async def mv():
            results["move"] = await ad.call("move_to", {"x": 103, "y": 65, "z": 102})

        async def fc():
            results["face"] = await ad.call("face", {"direction": "south"})

        async with anyio.create_task_group() as tg:
            tg.start_soon(mv)
            tg.start_soon(fc)
        return results

    _, ad = _run(sim, tmp_path, script)
    assert ad.pose.pos == sim.pos and ad.pose.facing == sim.facing
    assert results["move"]["ok"] and results["face"]["ok"]
    assert sim.pos == (103, 65, 102)


def test_bad_addition_arguments_give_envelope(tmp_path):
    async def script(ad):
        return (await ad.call("move_to", {"x": 1}),
                await ad.call("move_to", {"x": 1, "y": 2, "z": 3, "speed": 9}),
                await ad.call("get_action_log", {"last_n": "abc"}))

    envs, ad = _run(make_sim(), tmp_path, script)
    for env in envs:
        assert env["ok"] is False and env["error_code"] == "BLOCKED"
        assert env["message"].startswith("bad argument: ")
    assert [e["tool"] for e in ad.log.entries] == ["move_to", "move_to", "get_action_log"]


def test_move_to_counts_real_steps_on_detour(tmp_path):
    sim = make_sim(setup={(100, 64, 103): STONE, (100, 65, 103): STONE})

    async def script(ad):
        return await ad.call("move_to", {"x": 100, "y": 64, "z": 101})

    env, _ = _run(sim, tmp_path, script)
    assert env["ok"], env
    assert env["data"]["steps"] == 6  # обход сбоку: 4 вперёд и 2 вбок, а не 4 по прямой


def test_failed_dig_move_keeps_dug(tmp_path):
    # Стена 5x3: обойти или перелететь стоит +6 шагов, прокопать +4, поэтому путь копает (100, 64, 104).
    wall = {(x, y, 104): STONE for x in range(98, 103) for y in range(64, 67)}
    sim = make_sim(setup=wall)

    async def script(ad):
        sim.occ[(100, 64, 102)] = STONE  # препятствие, о котором карта не знает
        return await ad.call("move_to", {"x": 100, "y": 64, "z": 101, "policy": "dig_through"})

    env, ad = _run(sim, tmp_path, script)
    assert env["ok"] is False
    assert [100, 64, 104] in env["data"]["dug"]
    assert ad.log.entries[-1]["data"]["dug"] == env["data"]["dug"]
