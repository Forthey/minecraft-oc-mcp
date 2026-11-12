"""RobotAdapter: вызовы агента поверх oc-mcp.

Сквозной tool уходит в oc-mcp как есть. Ответ заворачивается в конверт, текст ошибки
переводится в код (codes.py), data дополняется тем, что адаптер может вывести сам:
позицией из pose, слотами из текста, JSON. Добавки (additions.py) пользуются raw,
поэтому их внутренние вызовы не попадают в журнал агента.
"""

from __future__ import annotations

import logging
import time

import anyio
import jsonschema

from adapter.action_log import ActionLog
from adapter.codes import classify
from adapter.parse import parse_json, parse_moved, parse_slots, parse_storage
from adapter.pose import Pose
from adapter.upstream import Upstream
from adapter.worldmap import NoMap, WorldMap

log = logging.getLogger(__name__)

# Коды, после которых состояние робота неизвестно и позицию надо перечитать.
RESYNC_CODES = {"CONNECTION_LOST", "UNKNOWN"}
JSON_TOOLS = {"world_info", "nei_find", "nei_recipes", "nei_recipe", "nei_craft_tree", "nei_machine_plan"}


def ok(message: str, data: dict | None = None) -> dict:
    return {"ok": True, "message": message, "data": data or {}}


def err(code: str, message: str, data: dict | None = None) -> dict:
    return {"ok": False, "error_code": code, "message": message, "data": data or {}}


class RobotAdapter:
    """Состояние адаптера: связь с oc-mcp, pose, карта и журнал."""

    def __init__(self, upstream: Upstream, worldmap: WorldMap | None = None, log: ActionLog | None = None,
                 pathfinder=None, link=None):
        self.up = upstream
        self.pathfinder = pathfinder
        self.link = link
        self.map = worldmap or NoMap()
        self.log = log or ActionLog(None)
        self.pose = Pose()
        # Почему позиция неизвестна: no_navigation (нет Navigation Upgrade) или no_response (робот молчит).
        self.pose_status = "unknown"
        self.pose_error = None
        # Вызовы агента идут строго по одному: MCP-сервер обрабатывает запросы параллельно,
        # а добавка из нескольких шагов не должна перемежаться с другим вызовом.
        self._lock: anyio.Lock | None = None

    async def start(self) -> None:
        """Читает позицию робота. Без Navigation Upgrade она остаётся неизвестной."""
        await self.sync()

    async def sync(self) -> bool:
        """Перечитывает позицию через world_info. Неудача делает позицию неизвестной."""
        good, text, _ = await self.up.call("world_info", {})
        info = parse_json(text) if good else None
        tracked = self.pose.pos if self.pose_status == "waypoint" else None
        if self.pose.sync(info or {}):
            self.pose_status = "waypoint" if self.pose.source == "waypoint" else "ok"
            self.pose_error = None
            if self.pose.source == "waypoint":
                log.info("robot position %s calibrated by waypoint", self.pose.pos)
            return True
        if tracked is not None and (info or {}).get("facing") == self.pose.facing:
            self.pose.pos = tracked
            self.pose.source = "waypoint"
            return True
        self.pose.pos = None
        self.pose_status = "no_navigation" if good else "no_response"
        self.pose_error = (info or {}).get("position_error")
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
        before = self.pose.pos if self.pose.known else None
        good, text, code = await self.up.call(name, args)
        data = self._data(name, args, good, text)
        self._explore(name, args, good, text, before)
        if good:
            if name in ("place", "swing"):
                self.map.invalidate()
            return ok(text, data)
        code = code or classify(text)
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
                if self.pose.sync(info):
                    self.pose_status = "waypoint" if self.pose.source == "waypoint" else "ok"
                if self.pose.source == "waypoint" and self.pose.known:
                    info = {**info, "x": self.pose.pos[0], "y": self.pose.pos[1], "z": self.pose.pos[2],
                            "pose_source": "waypoint"}
            return info
        return {}

    def _explore(self, name: str, args: dict, good: bool, text: str, before) -> None:
        m = self.map
        if name == "world_info" and good and self.link is not None and self.link.ctx_id is None:
            robot_id = (parse_json(text) or {}).get("robot_id")
            if robot_id:
                self.link.robot_id = robot_id
        if not hasattr(m, "flush") or not self.pose.known:
            return
        if name == "move" and before is not None and not text.startswith("bad argument: "):
            side = {"forward": "front", "back": "back", "up": "up", "down": "down"}.get(args.get("direction"))
            d = self.pose.side_dir(side) if side else None
            if d is not None:
                k = int(args.get("n", 1)) if good else (parse_moved(text) or 0)
                cell = before
                for _ in range(k):
                    cell = (cell[0] + d[0], cell[1] + d[1], cell[2] + d[2])
                    m.mark(cell, "air", source="move")
                if not good:
                    m.on_move_blocked(self.pose, args["direction"])
        elif not good:
            return
        elif name == "place":
            m.on_place(self.pose, args.get("side", "front"))
        elif name == "swing":
            m.on_swing(self.pose, args.get("side", "front"))
        elif name == "geo_scan":
            m.ingest_geo_scan(self.pose, args, text)
        elif name == "surroundings":
            for pos, _, block in m.ingest_surroundings(self.pose, text):
                if block and self.link is not None:
                    self.link.report_hazard(pos, block)
        else:
            return
        m.flush()

    def _action_log(self, last_n: int) -> dict:
        actions = [{"tool": e["tool"], "args": e["args"], "ok": e["ok"], "error_code": e["error_code"]}
                   for e in self.log.entries[-last_n:]]
        return ok("actions", {"actions": actions})
