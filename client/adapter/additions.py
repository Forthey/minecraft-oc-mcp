"""Добавки контракта v2: высокоуровневые tools в мировых координатах поверх oc-mcp.

Каждая добавка это асинхронная функция (adapter, **args) -> конверт. Она пользуется
adapter.raw, поэтому её внутренние вызовы oc-mcp не попадают в журнал агента.
Путь ищется по карте (adapter.map), позиция берётся из adapter.pose.
"""

from __future__ import annotations

import re

from adapter.parse import item_key, parse_moved, parse_slots
from adapter.pathfinding import NEIGHBOURS, astar
from adapter.pose import DIRS, FACINGS, Pos
from adapter.robot import err, ok

MOVE_MAX = 64
DIG_COST = 5.0
REPLANS = 2
VERIFY_PAGE = 50
ITEM_RE = re.compile(r"^[A-Za-z0-9_]+:[A-Za-z0-9_./-]+(:\d+)?$")
NO_POSE = "robot position unknown: navigation upgrade required"
NO_MAP = "no world map"
NO_RESPONSE = "robot does not respond: position unknown"


def _sub(a: Pos, b: Pos) -> Pos:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Pos, b: Pos) -> Pos:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _nei(item: str) -> str:
    parts = item.split(":")
    return item if len(parts) >= 3 and parts[-1].isdigit() else f"{item}:0"


async def _missing(ad, need_map: bool = True) -> dict | None:
    """Конверт ошибки, если нет позиции робота или карты.

    Позиция читается лениво: адаптер отвечает агенту сразу, не дожидаясь робота. Если
    world_info не ответил, это CONNECTION_LOST, а не отсутствие Navigation Upgrade.
    """
    if not ad.pose.known:
        await ad.sync()
    if not ad.pose.known:
        if ad.pose_status == "no_response":
            return err("CONNECTION_LOST", NO_RESPONSE)
        return err("UNSUPPORTED", NO_POSE)
    if need_map and not ad.map.available:
        return err("UNSUPPORTED", NO_MAP)
    return None


def _direction_of(d: Pos) -> str:
    return next(name for name, v in DIRS.items() if v == d)


async def face(ad, direction: str) -> dict:
    if direction not in FACINGS:
        return err("BLOCKED", f"unknown direction {direction}, use north, south, east or west")
    if (problem := await _missing(ad, need_map=False)) is not None:
        return problem
    turn = ad.pose.turn_to(direction)
    if turn is not None:
        env = await ad.raw("turn", {"direction": turn})
        if not env["ok"]:
            return env
    return ok(f"Facing {direction}.", {"facing": ad.pose.facing})


def _path(ad, start: Pos, goal: Pos, policy: str) -> list[Pos] | None:
    def cost(p: Pos):
        if not ad.map.region_contains(p):
            return None
        if not ad.map.occupied(p):
            return 1.0
        return DIG_COST if policy == "dig_through" else None

    return astar(start, goal, cost)


async def _step(ad, d: Pos, n: int, walked: list[int]) -> dict:
    """n шагов в направлении d: вертикально move up/down, горизонтально face и move forward.

    walked[0] копит сделанные шаги, включая неполный ход.
    """
    direction = _direction_of(d)
    if direction in ("up", "down"):
        move_dir = direction
    else:
        env = await face(ad, direction)
        if not env["ok"]:
            return env
        move_dir = "forward"
    left = n
    env = ok("")
    while left > 0:
        k = min(left, MOVE_MAX)
        env = await ad.raw("move", {"direction": move_dir, "n": k})
        if not env["ok"]:
            walked[0] += parse_moved(env["message"]) or 0
            return env
        walked[0] += k
        left -= k
    return env


async def _dig(ad, d: Pos) -> dict:
    """Ломает блок в направлении d перед шагом в занятую клетку."""
    direction = _direction_of(d)
    if direction in ("up", "down"):
        return await ad.raw("swing", {"side": direction})
    env = await face(ad, direction)
    return env if not env["ok"] else await ad.raw("swing", {"side": "front"})


async def _follow(ad, path: list[Pos], policy: str, dug: list, walked: list[int]) -> dict:
    """Проходит путь отрезками. Занятые клетки при dig_through ломаются по одной."""
    i = 0
    while i < len(path) - 1:
        d = _sub(path[i + 1], path[i])
        if policy == "dig_through" and ad.map.occupied(path[i + 1]):
            env = await _dig(ad, d)
            if not env["ok"]:
                return env
            dug.append(list(path[i + 1]))
            env = await _step(ad, d, 1, walked)
            if not env["ok"]:
                return env
            i += 1
            continue
        n = 1
        while (i + n < len(path) - 1 and _sub(path[i + n + 1], path[i + n]) == d
               and not (policy == "dig_through" and ad.map.occupied(path[i + n + 1]))):
            n += 1
        env = await _step(ad, d, n, walked)
        if not env["ok"]:
            return env
        i += n
    return ok("")


async def move_to(ad, x: int, y: int, z: int, policy: str = "avoid") -> dict:
    if (problem := await _missing(ad)) is not None:
        return problem
    target = (int(x), int(y), int(z))
    if not ad.map.region_contains(target):
        return err("OUT_OF_RANGE", f"{list(target)} is outside the allowed area")
    if policy not in ("avoid", "dig_through"):
        return err("BLOCKED", f"unknown policy {policy}")
    if policy == "avoid" and ad.map.occupied(target):
        return err("BLOCKED", f"{list(target)} is occupied")
    dug: list = []
    walked = [0]

    def failed(env: dict) -> dict:
        # Ответ с ошибкой тоже несёт сломанные блоки: их считает метрика dig_near_structure.
        data = dict(env.get("data") or {})
        if ad.pose.known:
            data["pos"] = list(ad.pose.pos)
        return {**env, "data": {**data, "steps": walked[0], "dug": dug}}

    last = None
    for _ in range(REPLANS + 1):
        path = _path(ad, ad.pose.pos, target, policy)
        if path is None:
            return failed(err("NO_PATH", f"no route to {list(target)} with policy {policy}", {"from": list(ad.pose.pos)}))
        last = await _follow(ad, path, policy, dug, walked)
        if last["ok"]:
            return ok(f"Moved to {list(target)} in {walked[0]} steps.",
                      {"pos": list(ad.pose.pos), "steps": walked[0], "dug": dug})
        if last.get("error_code") != "BLOCKED":
            return failed(last)
        # В мире препятствие, которого не было на карте: перечитать карту и строить заново.
        ad.map.invalidate()
    return failed(last)


async def place_at(ad, x: int, y: int, z: int, item: str, from_: str | None = None) -> dict:
    target = (int(x), int(y), int(z))
    if not ITEM_RE.match(item):
        return err("UNKNOWN_ITEM", f"unknown item {item}")
    if (problem := await _missing(ad)) is not None:
        return problem
    if not ad.map.region_contains(target):
        return err("OUT_OF_RANGE", f"{list(target)} is outside the allowed area")
    inv = await ad.raw("inventory_scan", {})
    if not inv["ok"]:
        return inv
    slot = next((s["slot"] for s in parse_slots(inv["message"]) if item_key(s["name"]) == item_key(item)), None)
    if slot is None:
        return err("NO_ITEM", f"no {_nei(item)} in the robot inventory")
    if ad.map.occupied(target):
        return err("CANT_PLACE", f"{list(target)} is occupied")
    if from_ is not None:
        if from_ not in DIRS:
            return err("BLOCKED", f"unknown approach side {from_}")
        approaches = [_add(target, DIRS[from_])]
    else:
        approaches = [_add(target, d) for d in NEIGHBOURS]
    best = None
    for a in approaches:
        if not ad.map.region_contains(a) or (ad.map.occupied(a) and a != ad.pose.pos):
            continue
        path = _path(ad, ad.pose.pos, a, "avoid")
        if path is not None and (best is None or len(path) < len(best)):
            best = path
    if best is None:
        return err("NO_PATH", f"no free approach to {list(target)}", {"from": list(ad.pose.pos)})
    if best[-1] != ad.pose.pos:
        moved = await move_to(ad, *best[-1])
        if not moved["ok"]:
            return moved
    d = _sub(target, ad.pose.pos)
    direction = _direction_of(d)
    if direction in ("up", "down"):
        side = direction
    else:
        turned = await face(ad, direction)
        if not turned["ok"]:
            return turned
        side = "front"
    placed = await ad.raw("place", {"side": side, "slot": slot})
    if not placed["ok"]:
        return placed
    return ok(f"Placed {_nei(item)} at {list(target)} from slot {slot}.", {"pos": list(target), "slot": slot})


async def get_status(ad) -> dict:
    await ad.sync()
    if (problem := await _missing(ad, need_map=False)) is not None:
        return problem
    inv = await ad.raw("inventory_scan", {})
    if not inv["ok"]:
        return inv
    inventory = [{"slot": s["slot"], "count": s["count"], "name": s["name"]} for s in parse_slots(inv["message"])]
    message = f"At {list(ad.pose.pos)} facing {ad.pose.facing}, {len(inventory)} inventory slots used."
    return ok(message, {"pos": list(ad.pose.pos), "facing": ad.pose.facing, "inventory": inventory})


async def verify_blocks(ad, expected: list[dict], page: int = 0) -> dict:
    if not ad.map.available:
        return err("UNSUPPORTED", NO_MAP)
    start = int(page) * VERIFY_PAGE
    chunk = expected[start:start + VERIFY_PAGE]
    missing, wrong = ad.map.verify(chunk)
    missing = [{"pos": list(e["pos"]), "item": _nei(e["item"])} for e in missing]
    wrong = [{"pos": list(e["pos"]), "item": _nei(e["item"])} for e in wrong]
    nxt = int(page) + 1 if start + VERIFY_PAGE < len(expected) else None
    return ok(f"Checked {len(chunk)}: {len(missing)} missing, {len(wrong)} wrong.",
              {"checked": len(chunk), "missing": missing, "wrong": wrong, "next_page": nxt})


async def search_docs(ad, query: str, mod: str | None = None, limit: int = 5) -> dict:
    return err("UNSUPPORTED", "no documentation service")


ADDITIONS = {
    "face": face,
    "move_to": move_to,
    "place_at": place_at,
    "get_status": get_status,
    "verify_blocks": verify_blocks,
    "search_docs": search_docs,
}
