"""Разбор текстов oc-mcp. Тексты получаются из RobotSim стенда, она отвечает строками Lua."""

import copy

import pytest

from adapter.parse import item_key, parse_json, parse_moved, parse_slots, parse_storage
from stand.fake_mcp.sim import RobotSim
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.scenario import SCENARIOS_DIR, load_scenario
from stand.world.backend import MemoryWorld


@pytest.fixture()
def sim():
    s = copy.deepcopy(load_scenario(SCENARIOS_DIR / "s01-wall" / "scenario.yaml"))
    s.robot["pos"] = [96, 64, 105]
    s.robot["facing"] = "west"
    s.robot["inventory"] = [{"item": "minecraft:cobblestone", "count": 9}, {"item": "minecraft:planks:1", "count": 4}]
    return RobotSim(s, Knowledge.load(KNOWLEDGE_DIR), MemoryWorld(s.scene_blocks()))


def test_parse_slots(sim):
    slots = parse_slots(sim.inventory_scan()["message"])
    assert slots[0] == {"slot": 1, "count": 9, "name": "minecraft:cobblestone:0", "label": "Cobblestone"}
    assert slots[1]["name"] == "minecraft:planks:1" and slots[1]["count"] == 4
    assert parse_slots("Robot inventory is empty.") == []


def test_parse_slots_keeps_damage_when_printed():
    assert parse_slots("slot 3: 1x IC2:blockMachine:3 (Macerator)")[0]["name"] == "IC2:blockMachine:3"


def test_parse_storage(sim):
    st = parse_storage(sim.storage_scan("front")["message"])
    assert st["block"] == "minecraft:chest" and st["size"] == 27
    assert st["slots"] == [{"slot": 1, "count": 32, "name": "minecraft:cobblestone:0", "label": "Cobblestone"}]
    assert parse_storage("Storage has 2 slots.\nStorage is empty.") == {"block": None, "size": 2, "slots": []}


def test_parse_moved():
    assert parse_moved("moved 2 of 3 blocks forward, blocked: solid") == 2
    assert parse_moved("Moved up 2 blocks.") is None


def test_parse_json(sim):
    assert parse_json(sim.world_info()["message"])["x"] == 96
    assert parse_json("not json") is None


def test_item_key():
    assert item_key("minecraft:cobblestone") == item_key("minecraft:cobblestone:0") == "minecraft:cobblestone"
    assert item_key("IC2:blockMachine:3") == "IC2:blockMachine"
