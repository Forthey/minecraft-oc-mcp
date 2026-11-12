"""Описания и JSON Schema добавок адаптера для list_tools.

Схемы tools oc-mcp адаптер берёт из самого oc-mcp. Эти совпадают со схемами fake-MCP
стенда (stand/fake_mcp/dispatch.py), это проверяет тест test_addition_specs_match_fake.
"""

from __future__ import annotations

DIR4 = {"type": "string", "enum": ["north", "south", "east", "west"]}
DIR6 = {"type": "string", "enum": ["north", "south", "east", "west", "up", "down"]}
ITEM = {"type": "string", "description": "Item id: mod:name:damage or mod:name"}
TEXT = {"type": "string"}
INT = {"type": "integer"}
POS = {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3}
LIMIT = {"type": "integer", "minimum": 1, "maximum": 50}
SCAN_AREA_DESCRIPTION = ("Scan a world-coordinate box (corners x1,y1,z1 and x2,y2,z2, inclusive, at most 4096 cells) "
                         "with the geolyzer in <=64-block chunks. Returns data.solid as [x, y, z, hardness] of "
                         "non-air cells (hardness only, no names) and data.skipped for chunks farther than 32 "
                         "blocks from the robot. Use surroundings for exact names of adjacent blocks.")


def _obj(required: list[str], **props) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


def _spec(description: str, schema: dict) -> dict:
    return {"description": description, "inputSchema": schema}


ADDITION_SPECS: dict[str, dict] = {
    "get_status": _spec("Position, facing and inventory slots of the robot.", _obj([])),
    "move_to": _spec("Pathfinding move to a world position. policy: avoid or dig_through.",
                     _obj(["x", "y", "z"], x=INT, y=INT, z=INT,
                          policy={"type": "string", "enum": ["avoid", "dig_through"]})),
    "face": _spec("Turn to north, south, east or west.", _obj(["direction"], direction=DIR4)),
    "place_at": _spec("Move next to the target and place item there. from sets the approach side.",
                      _obj(["x", "y", "z", "item"], x=INT, y=INT, z=INT, item=ITEM, **{"from": DIR6})),
    "search_docs": _spec("Search mod documentation about mechanics, multiblocks and machine setup.",
                         _obj(["query"], query=TEXT, mod=TEXT, limit=LIMIT)),
    "verify_blocks": _spec("Compare a list [{pos, item}] with the world. Returns missing / wrong, 50 per page.",
                           _obj(["expected"], expected={"type": "array", "items": {
                               "type": "object", "required": ["pos", "item"], "properties": {"pos": POS, "item": ITEM}}},
                               page=INT)),
    "scan_area": _spec(SCAN_AREA_DESCRIPTION,
                       _obj(["x1", "y1", "z1", "x2", "y2", "z2"], x1=INT, y1=INT, z1=INT, x2=INT, y2=INT, z2=INT)),
    "get_action_log": _spec("Last last_n robot actions with results.",
                            _obj([], last_n={"type": "integer", "minimum": 1})),
}
