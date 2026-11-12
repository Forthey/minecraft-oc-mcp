"""Тексты ответов tools oc-mcp, скопированные из его Lua-кода (lua/oc_mcp/tools).

fake-MCP отвечает этими же строками, чтобы агент видел одинаковые сообщения на
стенде и с настоящим роботом. Адаптер к oc-mcp переводит их в коды ошибок, поэтому
при изменении строк в oc-mcp их надо поправить здесь и в адаптере вместе.
"""

from __future__ import annotations

NO_TOOL = "no tool equipped"


def moved(direction: str, n: int) -> str:
    return f"Moved {direction} {n} blocks."


def moved_partial(moved_n: int, n: int, direction: str, reason: str = "solid") -> str:
    return f"moved {moved_n} of {n} blocks {direction}, blocked: {reason}"


def turned(direction: str) -> str:
    return f"Turned {direction}."


def slot_empty(slot: int) -> str:
    return f"slot {slot} is empty, nothing to place"


def place_occupied(slot: int, side: str, block: str) -> str:
    return (f"cannot place from slot {slot} {side}: block in the way; {side} is occupied by {block} "
            "(break it with swing first)")


def place_failed(slot: int, side: str, why: str) -> str:
    return f"cannot place from slot {slot} {side}: {why}"


def placed(slot: int, side: str, block: str, left: int) -> str:
    return f"Placed from slot {slot} {side}: {block}. {left} left in slot {slot}."


def swing_air(side: str) -> str:
    return f"nothing to hit on {side} (air)"


def swing_cannot_break(block: str, side: str, tool: str = NO_TOOL) -> str:
    return (f"cannot break {block} ({side}) with the equipped tool ({tool}). "
            "Equip a suitable tool (e.g. a pickaxe for stone/furnaces) with equip.")


def swing_failed(side: str, what: str) -> str:
    return f"swing {side} failed: {what}"


def broke(block: str, side: str, tool: str = NO_TOOL) -> str:
    return f"Broke {block} ({side}); drops went to the inventory. {tool}."


def used(side: str, what: str = "nothing") -> str:
    return f"Used {side}: {what}."


GEO_SCAN_TOO_BIG = "width*depth*height must be <= 64"
NO_ENERGY = "not enough energy"


# Инвентарь и хранилища.

INVENTORY_EMPTY = "Robot inventory is empty."
STORAGE_EMPTY = "Storage is empty."


def item_line(slot: int, count: int, name: str, label: str) -> str:
    return f"slot {slot}: {count}x {name} ({label})"


def storage_header(block: str, size: int) -> str:
    return f"Block: {block}\nStorage has {size} slots."


def no_storage(side: str) -> str:
    return f"no storage on side {side}"


def take_failed(side: str, slot: int, reason: str) -> str:
    return f"cannot take items from {side} slot {slot}: {reason}"


def took(side: str, slot: int) -> str:
    return f"Took items from {side} slot {slot}."


def put_failed(side: str, reason: str) -> str:
    return f"cannot put items {side}: {reason}"


def put_done(robot_slot: int, side: str) -> str:
    return f"Put items from robot slot {robot_slot} {side}."


def transfer_failed(from_slot: int, to_slot: int, reason: str) -> str:
    return f"cannot move items from slot {from_slot} to slot {to_slot}: {reason}"


def transferred(from_slot: int, to_slot: int) -> str:
    return f"Moved items from slot {from_slot} to slot {to_slot}."


def equip_failed(slot: int) -> str:
    return f"cannot equip from slot {slot}"


def equipped(slot: int) -> str:
    return f"Swapped slot {slot} with the tool slot."


# Крафт.

GRID_EMPTY = "crafting grid is empty (grid slots are 1,2,3 / 5,6,7 / 9,10,11)"
CRAFTED = "Crafted. Use inventory_scan to see the result."
NO_RESULT_SLOT = "no free slot outside the crafting grid for the result"


def no_grid_match(grid: str) -> str:
    return f"no recipe matches the grid, or there is no free slot for the result. Current grid:\n{grid}"


def not_crafting_recipe(cat: str) -> str:
    return f"not a crafting-table recipe (category {cat}); use nei_machine_plan for machines"


def ingredients_missing(missing: list[str]) -> str:
    return ("not enough ingredients in the robot inventory, missing: " + ", ".join(missing)
            + ". The grid is partly laid out; get the items and call craft_recipe again.")


def missing_entry(n: int, label: str, slot: int) -> str:
    return f"{n}x {label} (grid slot {slot})"


def no_room_for_grid(slot: int) -> str:
    return f"no room outside the crafting grid for the items in slot {slot}"


def crafted_recipe(count: int, slot: int, n: int, item: str, label: str) -> str:
    return f"Crafted {count} time(s): slot {slot} now holds {n}x {item} ({label})."


def count_too_large(slot: int, need: int) -> str:
    return f"count too large: slot {slot} would need {need} items, max 64"
