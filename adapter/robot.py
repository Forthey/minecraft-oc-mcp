"""RobotAdapter: вызовы агента поверх oc-mcp.

Сквозной tool уходит в oc-mcp как есть. Ответ заворачивается в конверт, текст ошибки
переводится в код (codes.py), data дополняется тем, что адаптер может вывести сам:
позицией из pose, слотами из текста, JSON. Добавки (additions.py) пользуются raw,
поэтому их внутренние вызовы не попадают в журнал агента.
"""

from __future__ import annotations

import time

import anyio
import jsonschema

from adapter.action_log import ActionLog
from adapter.codes import classify
from adapter.parse import parse_json, parse_moved, parse_slots, parse_storage
from adapter.pose import Pose
from adapter.upstream import Upstream
from adapter.worldmap import NoMap, WorldMap

# Коды, после которых состояние робота неизвестно и позицию надо перечитать.
RESYNC_CODES = {"CONNECTION_LOST", "UNKNOWN"}
JSON_TOOLS = {"world_info", "nei_find", "nei_recipes", "nei_recipe", "nei_craft_tree", "nei_machine_plan"}


def ok(message: str, data: dict | None = None) -> dict:
    return {"ok": True, "message": message, "data": data or {}}


def err(code: str, message: str, data: dict | None = None) -> dict:
    return {"ok": False, "error_code": code, "message": message, "data": data or {}}


class RobotAdapter:
    """Состояние адаптера: связь с oc-mcp, pose, карта и журнал."""

    def __init__(self, upstream: Upstream, worldmap: WorldMap | None = None, log: ActionLog | None = None):
        self.up = upstream
        self.map = worldmap or NoMap()
        self.log = log or ActionLog(None)
        self.pose = Pose()
        # Почему позиция неизвестна: no_navigation (нет Navigation Upgrade) или no_response (робот молчит).
        self.pose_status = "unknown"
        # Вызовы агента идут строго по одному: MCP-сервер обрабатывает запросы параллельно,
        # а добавка из нескольких шагов не должна перемежаться с другим вызовом.
        self._lock: anyio.Lock | None = None

    async def start(self) -> None:
        """Читает позицию робота. Без Navigation Upgrade она остаётся неизвестной."""
        await self.sync()

    async def sync(self) -> bool:
        """Перечитывает позицию через world_info. Неудача делает позицию неизвестной."""
        good, text = await self.up.call("world_info", {})
        info = parse_json(text) if good else None
        if self.pose.sync(info or {}):
            self.pose_status = "ok"
            return True
        self.pose.pos = None
        self.pose_status = "no_navigation" if good else "no_response"
        return False

    async def call(self, name: str, args: dict | None) -> dict:
        """Вызов агента: tool oc-mcp или добавка. Пишется в журнал."""
        if self._lock is None:
            self._lock = anyio.Lock()
        args = dict(args or {})
        async with self._lock:
            start = time.perf_counter()
            try:
                env = await self._dispatch(name, args)
            except Exception as e:  # noqa: BLE001 - адаптер отвечает конвертом, а не падает
                env = err("UNKNOWN", f"adapter error: {type(e).__name__}: {e}")
            self.log.append(name, args, env, (time.perf_counter() - start) * 1000)
        return env

    async def _dispatch(self, name: str, args: dict) -> dict:
        from adapter.additions import ADDITIONS
        from adapter.tools import ADDITION_SPECS

        if name in ADDITION_SPECS:
            # Схему tools oc-mcp проверяет сам мост, схему добавок проверяем здесь, как fake-MCP.
            try:
                jsonschema.validate(args, ADDITION_SPECS[name]["inputSchema"])
            except jsonschema.ValidationError as e:
                return err("BLOCKED", f"bad argument: {e.message}")
        if name == "get_action_log":
            return self._action_log(int(args.get("last_n", 20)))
        if name in ADDITIONS:
            return await ADDITIONS[name](self, **{("from_" if k == "from" else k): v for k, v in args.items()})
        return await self.raw(name, args)

    async def raw(self, name: str, args: dict) -> dict:
        """Вызов tool oc-mcp без журнала: конверт, код ошибки, data, обновление pose и карты."""
        good, text = await self.up.call(name, args)
        data = self._data(name, args, good, text)
        if good:
            if name in ("place", "swing"):
                self.map.invalidate()
            return ok(text, data)
        code = classify(text)
        if code in RESYNC_CODES:
            await self.sync()
        return err(code, text, data)

    def _data(self, name: str, args: dict, good: bool, text: str) -> dict:
        if not good and text.startswith("bad argument: "):
            # Мост отклонил аргументы, команда до робота не дошла.
            return {}
        if name == "move" and self.pose.known:
            k = int(args.get("n", 1)) if good else parse_moved(text)
            if k:
                self.pose.apply_move(args["direction"], k)
            return {"pos": list(self.pose.pos), "facing": self.pose.facing}
        if name == "turn" and good and self.pose.known:
            self.pose.apply_turn(args["direction"])
            return {"pos": list(self.pose.pos), "facing": self.pose.facing}
        if not good:
            return {}
        if name in ("place", "swing") and self.pose.known:
            target = self.pose.side_pos(args.get("side", "front"))
            return {"pos": list(target)} if target else {}
        if name == "inventory_scan":
            return {"slots": parse_slots(text)}
        if name == "storage_scan":
            return parse_storage(text)
        if name in JSON_TOOLS:
            info = parse_json(text) or {}
            if name == "world_info":
                self.pose.sync(info)
            return info
        return {}

    def _action_log(self, last_n: int) -> dict:
        actions = [{"tool": e["tool"], "args": e["args"], "ok": e["ok"], "error_code": e["error_code"]}
                   for e in self.log.entries[-last_n:]]
        return ok("actions", {"actions": actions})
