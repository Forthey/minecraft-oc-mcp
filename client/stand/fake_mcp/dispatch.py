"""Диспетчер fake-MCP: схемы tools, профили, внедрение сбоев и action log.

Набор TOOL_SPECS обязан совпадать с skills/references/tool-contract.md, это
проверяет тест test_tool_specs_match_contract.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import jsonschema

from stand.fake_mcp.action_log import ActionLog
from stand.fake_mcp.envelope import err, ok
from stand.fake_mcp.profiles import PROFILES

SIDE = {"type": "string", "enum": ["front", "back", "left", "right", "up", "down"]}
DIR4 = {"type": "string", "enum": ["north", "south", "east", "west"]}
DIR6 = {"type": "string", "enum": ["north", "south", "east", "west", "up", "down"]}
ITEM = {"type": "string", "description": "Item id: mod:name or mod:name:meta"}
INT = {"type": "integer"}
COUNT = {"type": "integer", "minimum": 1}
POS = {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3}
BOX = {"type": "object", "required": ["from", "to"], "properties": {"from": POS, "to": POS}}
DETAIL = {"type": "string", "enum": ["summary", "full"]}


def _obj(required: list[str], **props) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


@dataclass(frozen=True)
class ToolSpec:
    """Группа (раздел контракта), описание для агента и JSON Schema аргументов."""

    group: str
    description: str
    schema: dict


TOOL_SPECS: dict[str, ToolSpec] = {
    "get_status": ToolSpec("state", "Position, facing, energy, tool durability, inventory summary (used slots, top items), warehouse position.", _obj([])),
    "inspect": ToolSpec("state", "Name and metadata of the adjacent block on side.", _obj(["side"], side=SIDE)),
    "scan_area": ToolSpec("state", "Summary of a region: air, solid, liquid, known blocks. detail=full lists blocks page by page.",
                          _obj(["box"], box=BOX, detail=DETAIL, page=INT)),
    "get_known_map": ToolSpec("state", "What the robot already remembers about a region, without scanning.", _obj(["box"], box=BOX, page=INT)),
    "move_to": ToolSpec("movement", "Pathfinding move. policy is avoid (never break blocks) or dig_through (break blocks in the way).",
                        _obj(["x", "y", "z"], x=INT, y=INT, z=INT, policy={"type": "string", "enum": ["avoid", "dig_through"]})),
    "move": ToolSpec("movement", "Low-level move n blocks in dir (forward, back, up, down). Fallback only.",
                     _obj(["dir"], dir={"type": "string", "enum": ["forward", "back", "up", "down"]}, n=COUNT)),
    "face": ToolSpec("movement", "Turn to north, south, east or west.", _obj(["dir"], dir=DIR4)),
    "dig": ToolSpec("world", "Break the block on side.", _obj(["side"], side=SIDE)),
    "place": ToolSpec("world", "Place item from inventory on side.", _obj(["item", "side"], item=ITEM, side=SIDE)),
    "place_at": ToolSpec("world", "Move next to the target and place item there. from optionally sets the side to approach from.",
                         _obj(["x", "y", "z", "item"], x=INT, y=INT, z=INT, item=ITEM, **{"from": DIR6})),
    "use": ToolSpec("world", "Right-click the block on side, optionally holding item.", _obj(["side"], side=SIDE, item=ITEM)),
    "list_inventory": ToolSpec("inventory", "Robot inventory. detail is summary or full.", _obj([], detail=DETAIL)),
    "inspect_container": ToolSpec("inventory", "Contents of the chest or machine on side, slot by slot.", _obj(["side"], side=SIDE)),
    "take": ToolSpec("inventory", "Take items from the container on side.",
                     _obj(["side", "item", "count"], side=SIDE, item=ITEM, count=COUNT, slot=INT)),
    "put": ToolSpec("inventory", "Put items into the container on side, optionally into a specific machine slot.",
                    _obj(["side", "item", "count"], side=SIDE, item=ITEM, count=COUNT, slot=INT)),
    "equip": ToolSpec("inventory", "Equip a tool.", _obj(["item"], item=ITEM)),
    "drop": ToolSpec("inventory", "Drop items in front of the robot.", _obj(["item", "count"], item=ITEM, count=COUNT)),
    "craft": ToolSpec("crafting", "Craft with the crafting upgrade. The tool arranges the 3x3 grid by itself.",
                      _obj(["item", "count"], item=ITEM, count=COUNT)),
    "search_items": ToolSpec("knowledge", "Search the item index (RAG).", _obj(["query"], query={"type": "string"}, limit=COUNT)),
    "get_item": ToolSpec("knowledge", "Item card: name, id, mod, short description.", _obj(["id"], id=ITEM)),
    "get_recipes": ToolSpec("knowledge", "Crafting table and machine recipes (NEI dump).", _obj(["item"], item=ITEM)),
    "plan_materials": ToolSpec("knowledge", "Crafting tree and what is still missing, counting the robot inventory and the warehouse when use_inventory is true.",
                               _obj(["item", "count"], item=ITEM, count=COUNT, use_inventory={"type": "boolean"})),
    "search_docs": ToolSpec("knowledge", "Search mod documentation about mechanics, multiblocks and machine setup (RAG).",
                            _obj(["query"], query={"type": "string"}, mod={"type": "string"}, limit=COUNT)),
    "verify_blocks": ToolSpec("verification", "Compare a list [{pos, item}] with the world. Returns a compact diff missing / wrong.",
                              _obj(["expected"], expected={"type": "array", "items": {
                                  "type": "object", "required": ["pos", "item"], "properties": {"pos": POS, "item": ITEM}}},
                                  page=INT)),
    "read_block_info": ToolSpec("verification", "State of the machine on side: energy, heat, active flag, slots.", _obj(["side"], side=SIDE)),
    "stop": ToolSpec("service", "Abort the current robot action.", _obj([])),
    "get_action_log": ToolSpec("service", "Last last_n robot actions with results.", _obj([], last_n=COUNT)),
}

# Имена аргументов контракта, которые совпадают с ключевыми словами Python.
ARG_RENAMES = {"from": "from_"}

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
        self.disabled = PROFILES[profile]
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
