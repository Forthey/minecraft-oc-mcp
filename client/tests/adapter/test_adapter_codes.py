"""Перевод текстов oc-mcp в коды контракта. Строки берутся из stand/fake_mcp/texts.py, это копия Lua oc-mcp."""

import pytest

from adapter.codes import classify
from stand.fake_mcp import texts

FAKE_TEXTS = [
    (texts.moved_partial(2, 3, "forward"), "BLOCKED"),
    (texts.slot_empty(2), "NO_ITEM"),
    (texts.place_occupied(1, "front", "minecraft:stone"), "BLOCKED"),
    (texts.place_failed(1, "front", "item is not a block"), "CANT_PLACE"),
    (texts.swing_air("front"), "BLOCKED"),
    (texts.swing_cannot_break("minecraft:bedrock", "front"), "TOOL_BROKEN"),
    (texts.no_storage("front"), "BLOCKED"),
    (texts.take_failed("front", 5, "slot is empty"), "NO_ITEM"),
    (texts.take_failed("front", 1, "robot inventory is full"), "INVENTORY_FULL"),
    (texts.take_failed("front", 1, "no inventory"), "BLOCKED"),
    (texts.put_failed("front", "inventory full"), "INVENTORY_FULL"),
    (texts.transfer_failed(1, 2, "slot 2 holds a different item"), "BLOCKED"),
    (texts.transfer_failed(3, 1, "slot 3 is empty"), "NO_ITEM"),
    (texts.transfer_failed(1, 4, "slot 4 is full"), "INVENTORY_FULL"),
    (texts.equip_failed(2), "NO_ITEM"),
    (texts.GRID_EMPTY, "NO_ITEM"),
    (texts.no_grid_match("[1: empty]"), "NO_RECIPE"),
    (texts.not_crafting_recipe("Smelting"), "NO_RECIPE"),
    (texts.ingredients_missing([texts.missing_entry(1, "Oak Wood Planks", 5)]), "NO_ITEM"),
    (texts.no_room_for_grid(1), "INVENTORY_FULL"),
    (texts.NO_RESULT_SLOT, "INVENTORY_FULL"),
]

BRIDGE_TEXTS = [
    ("OpenComputers did not respond within 120s. The command may still run later "
     "(singleplayer pauses when the game window loses focus): check the state, e.g. with inventory_scan, "
     "before retrying.", "CONNECTION_LOST"),
    ("tool geo_scan is disabled: missing component: geolyzer", "UNSUPPORTED"),
    ("NO_PROVIDER: no player with the mod is online and the answer is not cached", "NO_PROVIDER"),
    ("UNKNOWN_ITEM: unknown item: foo:bar", "UNKNOWN_ITEM"),
    ("UNKNOWN_RECIPE: unknown recipe: r0000000000000000", "NO_RECIPE"),
    ("bad argument: direction is required", "BLOCKED"),
    ("something odd happened", "UNKNOWN"),
]


@pytest.mark.parametrize("text,code", FAKE_TEXTS + BRIDGE_TEXTS)
def test_text_maps_to_code(text, code):
    assert classify(text) == code
