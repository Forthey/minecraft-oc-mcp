"""Диспетчер fake-MCP: схемы tools, профили, внедрение сбоев и action log.

Набор TOOL_SPECS обязан совпадать с skills/references/tool-contract.md, это
проверяет тест test_tool_specs_match_contract.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import jsonschema

from adapter.tools import SCAN_AREA_DESCRIPTION
from stand.fake_mcp.action_log import ActionLog
from stand.fake_mcp.envelope import err, ok
from stand.fake_mcp.profiles import PROFILES

SIDE3 = {"type": "string", "enum": ["front", "up", "down"]}
DIR4 = {"type": "string", "enum": ["north", "south", "east", "west"]}
DIR6 = {"type": "string", "enum": ["north", "south", "east", "west", "up", "down"]}
ITEM = {"type": "string", "description": "Item id: mod:name:damage or mod:name"}
TEXT = {"type": "string"}
INT = {"type": "integer"}
SLOT = {"type": "integer", "minimum": 1}
COUNT = {"type": "integer", "minimum": 1, "maximum": 64}
POS = {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3}
BOOL = {"type": "boolean"}
OFFSET = {"type": "integer", "minimum": -32, "maximum": 32}
SIZE = {"type": "integer", "minimum": 1, "maximum": 64}
LIMIT = {"type": "integer", "minimum": 1, "maximum": 50}


def _obj(required: list[str], **props) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


@dataclass(frozen=True)
class ToolSpec:
    """Группа (раздел контракта), описание для агента и JSON Schema аргументов."""

    group: str
    description: str
    schema: dict

TOOL_SPECS: dict[str, ToolSpec] = {
    # Состояние
    "get_status": ToolSpec("state", "Position, facing and inventory slots of the robot.", _obj([])),
    "world_info": ToolSpec("state", "Robot id and name, world id, position and facing.", _obj([])),
    "surroundings": ToolSpec("state", "The six blocks next to the robot, relative to its facing.", _obj([])),
    "geo_scan": ToolSpec("state", "Hardness of a box around the robot, axes x = right, z = forward, y = up. width*depth*height <= 64.",
                         _obj([], x=OFFSET, z=OFFSET, y=OFFSET, width=SIZE, depth=SIZE, height=SIZE)),
    "scan_area": ToolSpec("state", SCAN_AREA_DESCRIPTION,
                          _obj(["x1", "y1", "z1", "x2", "y2", "z2"], x1=INT, y1=INT, z1=INT, x2=INT, y2=INT, z2=INT)),
    # Движение
    "move_to": ToolSpec("movement", "Pathfinding move to a world position. policy: avoid or dig_through.",
                        _obj(["x", "y", "z"], x=INT, y=INT, z=INT, policy={"type": "string", "enum": ["avoid", "dig_through"]})),
    "face": ToolSpec("movement", "Turn to north, south, east or west.", _obj(["direction"], direction=DIR4)),
    "move": ToolSpec("movement", "Move n blocks forward, back, up or down, stops at the first obstacle.",
                     _obj(["direction"], direction={"type": "string", "enum": ["forward", "back", "up", "down"]}, n=COUNT)),
    "turn": ToolSpec("movement", "Turn left, right or around.",
                     _obj(["direction"], direction={"type": "string", "enum": ["left", "right", "around"]})),
    # Мир
    "place_at": ToolSpec("world", "Move next to the target and place item there. from sets the approach side.",
                         _obj(["x", "y", "z", "item"], x=INT, y=INT, z=INT, item=ITEM, **{"from": DIR6})),
    "place": ToolSpec("world", "Place the block from a robot slot on side.", _obj([], side=SIDE3, slot=SLOT, sneaky=BOOL)),
    "swing": ToolSpec("world", "Break the block on side with the equipped tool, drops go to the inventory.",
                      _obj([], side=SIDE3, sneaky=BOOL)),
    "use": ToolSpec("world", "Right-click on side with the equipped tool.",
                    _obj([], side=SIDE3, sneaky=BOOL, duration={"type": "number", "minimum": 0, "maximum": 30})),
    # Инвентарь
    "inventory_scan": ToolSpec("inventory", "Non-empty robot slots.", _obj([])),
    "inventory_transfer": ToolSpec("inventory", "Move items between robot slots. A slot with another item is refused.",
                                   _obj(["from_slot", "to_slot"], from_slot=SLOT, to_slot=SLOT, count=COUNT)),
    "storage_scan": ToolSpec("inventory", "Non-empty slots of the chest or machine on side and its block id.", _obj([], side=SIDE3)),
    "storage_take": ToolSpec("inventory", "Take items from a slot of the storage on side.",
                             _obj(["side", "slot"], side=SIDE3, slot=SLOT, count=COUNT, robot_slot=SLOT)),
    "storage_put": ToolSpec("inventory", "Put items from a robot slot into the storage on side.",
                            _obj(["side", "robot_slot"], side=SIDE3, robot_slot=SLOT, count=COUNT, slot=SLOT)),
    "equip": ToolSpec("inventory", "Swap a robot slot with the tool slot.", _obj(["slot"], slot=SLOT)),
    # Крафт
    "craft_recipe": ToolSpec("crafting", "Craft a crafting-table recipe by its NEI recipe id, the grid is laid out automatically.",
                             _obj(["recipe"], recipe=TEXT, count=COUNT)),
    "craft": ToolSpec("crafting", "Low-level: craft what is laid out in grid slots 1,2,3 / 5,6,7 / 9,10,11.",
                      _obj([], count=COUNT, result_slot=SLOT)),
    # Знания
    "nei_find": ToolSpec("knowledge", "Find items by name, returns item ids with labels.",
                         _obj(["text"], text=TEXT, limit=LIMIT, lang=TEXT)),
    "nei_recipes": ToolSpec("knowledge", "All recipes that make the item, or with usages the recipes that use it.",
                            _obj(["item"], item=ITEM, usages=BOOL, category=TEXT, limit=LIMIT, cursor=TEXT, lang=TEXT)),
    "nei_recipe": ToolSpec("knowledge", "One recipe in full, with the robot slot for every grid cell.",
                           _obj(["recipe"], recipe=TEXT, lang=TEXT)),
    "nei_craft_tree": ToolSpec("knowledge", "Whole crafting tree: steps in order, raw materials, machines needed.",
                               _obj(["item"], item=ITEM, count={"type": "integer", "minimum": 1, "maximum": 1000000}, use_inventory=BOOL, lang=TEXT)),
    "nei_machine_plan": ToolSpec("knowledge", "Slots of the machine on side for the ingredients and the result of a recipe.",
                                 _obj(["recipe"], side=SIDE3, recipe=TEXT, times={"type": "integer", "minimum": 1}, lang=TEXT)),
    "search_docs": ToolSpec("knowledge", "Search mod documentation about mechanics, multiblocks and machine setup.",
                            _obj(["query"], query=TEXT, mod=TEXT, limit=LIMIT)),
    # Проверка
    "verify_blocks": ToolSpec("verification", "Compare a list [{pos, item}] with the world. Returns missing / wrong, 50 per page.",
                              _obj(["expected"], expected={"type": "array", "items": {
                                  "type": "object", "required": ["pos", "item"], "properties": {"pos": POS, "item": ITEM}}},
                                  page=INT)),
    # Служебные
    "get_action_log": ToolSpec("service", "Last last_n robot actions with results.", _obj([], last_n={"type": "integer", "minimum": 1})),
}
# Имена аргументов контракта, которые совпадают с ключевыми словами Python.
ARG_RENAMES = {"from": "from_"}

# Ответ OC NEI Bridge без игрока онлайн и без кэша (профиль no-nei).
NO_PROVIDER_MESSAGE = "NO_PROVIDER: no player with the mod is online and the answer is not cached"

FAULT_MESSAGES = {
    "CONNECTION_LOST": "connection to the robot was lost, the action may or may not have happened",
    "TIMEOUT": "the action did not finish in time, it may or may not have happened",
}


class Dispatcher:
    """Принимает вызов tool, применяет профиль и сбои, вызывает RobotSim, пишет action log."""

    def __init__(self, sim, profile: str, faults: list[dict], log: ActionLog):
        if profile not in PROFILES:
            raise ValueError(f"unknown profile {profile}")
        self.sim = sim
        self.disabled = PROFILES[profile]["disabled"]
        self.no_provider = PROFILES[profile]["no_provider"]
        self.faults = list(faults)
        self.log = log
        self.calls: dict[str, int] = {}

    def enabled_tools(self) -> list[str]:
        return [name for name in TOOL_SPECS if name not in self.disabled]

    def call(self, name: str, args: dict | None) -> dict:
        args = dict(args or {})
        start = time.perf_counter()
        fault = False
        if name not in TOOL_SPECS:
            env = err("BLOCKED", f"unknown tool {name}")
        elif name in self.disabled:
            env = err("BLOCKED", f"tool {name} is not available in this setup")
        else:
            self.calls[name] = self.calls.get(name, 0) + 1
            env, fault = self._run(name, args, self.calls[name])
        self.log.append(name, args, env, (time.perf_counter() - start) * 1000, fault)
        return env

    def _run(self, name: str, args: dict, n: int) -> tuple[dict, bool]:
        try:
            jsonschema.validate(args, TOOL_SPECS[name].schema)
        except jsonschema.ValidationError as e:
            return err("BLOCKED", f"bad argument: {e.message}"), False
        fault = next((f for f in self.faults if f["tool"] == name and f["call"] == n), None)
        if fault is not None and fault["effect"] == "skipped":
            return self._fault_env(fault), True
        if name in self.no_provider:
            return err("NO_PROVIDER", NO_PROVIDER_MESSAGE), False
        env = self._invoke(name, args)
        if fault is not None:
            return self._fault_env(fault), True
        return env, False

    def _invoke(self, name: str, args: dict) -> dict:
        if name == "get_action_log":
            return self._action_log(args.get("last_n", 20))
        kwargs = {ARG_RENAMES.get(k, k): v for k, v in args.items()}
        try:
            return getattr(self.sim, name)(**kwargs)
        except Exception as e:  # noqa: BLE001 - сервер не должен падать из-за ошибки в модели
            return err("BLOCKED", f"internal error in fake MCP: {type(e).__name__}: {e}")

    def _fault_env(self, fault: dict) -> dict:
        code = fault["error"]
        return err(code, FAULT_MESSAGES.get(code, f"injected failure {code}"))

    def _action_log(self, last_n: int) -> dict:
        actions = [
            {"tool": e["tool"], "args": e["args"], "ok": e["ok"], "error_code": e["error_code"]}
            for e in self.log.entries[-int(last_n):]
        ]
        return ok("actions", {"actions": actions})
