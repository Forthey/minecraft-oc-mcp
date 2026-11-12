"""Тестовый робот: обслуживает HTTP-опрос моста oc-mcp вместо Lua на роботе.

Протокол повторяет lua/oc_mcp/poller.lua: GET /poll отдаёт {"command": {...} | null},
команда исполняется, результат уходит POST /result как {"id", "ok", "text"} или
{"id", "ok", "error"}. Команда исполняется методом RobotSim с тем же именем, его
текст ответа это строки Lua oc-mcp (stand/fake_mcp/texts.py).
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from stand.fake_mcp.sim import RobotSim

SERVICE_KEYS = {"id", "type", "world_id"}


class RobotDouble:
    """Поток, который опрашивает мост и исполняет команды на RobotSim."""

    def __init__(self, sim: RobotSim, url: str, navigation: bool = True, disabled: dict[str, str] | None = None,
                 delay: float = 0.02):
        self.sim = sim
        self.url = url
        self.navigation = navigation
        self.disabled = dict(disabled or {})
        self.delay = delay
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _request(self, path: str, body: dict | None = None) -> dict | None:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=2) as resp:
                return json.loads(resp.read().decode() or "null")
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def _run(self) -> None:
        while not self._stop.is_set():
            reply = self._request("/poll")
            command = (reply or {}).get("command")
            if command:
                ok, text = self.handle(command)
                self._request("/result", {"id": command["id"], "ok": ok, ("text" if ok else "error"): text})
            else:
                self._stop.wait(self.delay)

    def handle(self, command: dict) -> tuple[bool, str]:
        """Исполняет команду моста и возвращает (ok, text), как run() Lua-tool."""
        name = command.get("type")
        if name in self.disabled:
            return False, f"tool {name} is disabled: {self.disabled[name]}"
        if name == "world_info" and not self.navigation:
            info = {"robot_id": "fake-robot", "robot_name": "robot", "world_id": command.get("world_id", "stand"),
                    "position_error": "no navigation upgrade: position unknown"}
            return True, json.dumps(info)
        method = getattr(self.sim, name, None)
        if method is None:
            return False, f"unknown command type: {name}"
        args = {k: v for k, v in command.items() if k not in SERVICE_KEYS}
        env = method(**args)
        return env["ok"], env["message"]
