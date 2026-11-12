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
WAYPOINT_RANGE = 32
EXPLORE_REPLANS = 64
VERIFY_PAGE = 50
SCAN_CHUNK = 4
SCAN_MAX = 4096
SCAN_RANGE = 32
ITEM_RE = re.compile(r"^[A-Za-z0-9_]+:[A-Za-z0-9_./-]+(:\d+)?$")
NO_POSE = "robot position unknown: navigation upgrade required"
WAYPOINT_SEARCH = 400
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
        reason = getattr(ad, "pose_error", None)
        if reason and not reason.startswith("no navigation upgrade"):
            return err("UNSUPPORTED", f"robot position unknown: {reason}. Place an OpenComputers Waypoint within "
                                      f"{WAYPOINT_SEARCH} blocks and label it with its coordinates, e.g. \"0 64 0\"")
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


def _long_range(ad, target: Pos) -> bool:
    pf = getattr(ad, "pathfinder", None)
    if pf is None or not ad.pose.known:
        return False
    return target != ad.pose.pos and max(abs(t - p) for t, p in zip(target, ad.pose.pos)) > pf.long_range


async def _long_leg(ad, target: Pos, walked: list[int]) -> dict:
    from adapter.java_pathfinding import densify

    route = await ad.pathfinder.route(ad.pose.pos, target, ad.pose.facing)
    if not route:
        return err("NO_PATH", f"long-range pathfinder found no route to {list(target)}", {"from": list(ad.pose.pos)})
    path = densify([ad.pose.pos, *route] if route[0] != ad.pose.pos else route)
    return await _follow(ad, path, "avoid", [], walked)


async def move_to(ad, x: int, y: int, z: int, policy: str = "avoid") -> dict:
    target = (int(x), int(y), int(z))
    if (problem := await _missing(ad, need_map=False)) is not None:
        return problem
    long_range = _long_range(ad, target)
    if not long_range and not ad.map.available:
        return err("UNSUPPORTED", NO_MAP)
    if policy not in ("avoid", "dig_through"):
        return err("BLOCKED", f"unknown policy {policy}")
    dug: list = []
    walked = [0]
    if long_range:
        leg = await _long_leg(ad, target, walked)
        if ad.pose.pos == target:
            return ok(f"Moved to {list(target)} in {walked[0]} steps.",
                      {"pos": list(ad.pose.pos), "steps": walked[0], "dug": dug})
        if not ad.map.available:
            if leg["ok"]:
                leg = err("NO_PATH", f"long-range route ended at {list(ad.pose.pos)}, not {list(target)}")
            data = {**(leg.get("data") or {}), "pos": list(ad.pose.pos), "steps": walked[0], "dug": dug}
            return {**leg, "data": data}
    if not ad.map.region_contains(target):
        return err("OUT_OF_RANGE", f"{list(target)} is outside the allowed area")
    if policy == "avoid" and ad.map.occupied(target):
        return err("BLOCKED", f"{list(target)} is occupied")

    def failed(env: dict) -> dict:
        # Ответ с ошибкой тоже несёт сломанные блоки: их считает метрика dig_near_structure.
        data = dict(env.get("data") or {})
        if ad.pose.known:
            data["pos"] = list(ad.pose.pos)
        return {**env, "data": {**data, "steps": walked[0], "dug": dug}}

    if not long_range:
        for hop in _hops(ad, target):
            if not (await _astar_leg(ad, hop, policy, dug, walked))["ok"]:
                break
    last = await _astar_leg(ad, target, policy, dug, walked)
    if last["ok"]:
        return ok(f"Moved to {list(target)} in {walked[0]} steps.",
                  {"pos": list(ad.pose.pos), "steps": walked[0], "dug": dug})
    return failed(last)


def _hops(ad, target: Pos) -> list[Pos]:
    link = getattr(ad, "link", None)
    if link is None or not link.enabled:
        return []
    pos = ad.pose.pos
    if max(abs(target[0] - pos[0]), abs(target[2] - pos[2])) <= WAYPOINT_RANGE:
        return []
    return [h for h in link.route_hint(pos, target) if ad.map.region_contains(h) and not ad.map.occupied(h)]


async def _astar_leg(ad, target: Pos, policy: str, dug: list, walked: list[int]) -> dict:
    last = None
    replans = EXPLORE_REPLANS if hasattr(ad.map, "mark") else REPLANS
    for _ in range(replans + 1):
        path = _path(ad, ad.pose.pos, target, policy)
        if path is None:
            return err("NO_PATH", f"no route to {list(target)} with policy {policy}", {"from": list(ad.pose.pos)})
        last = await _follow(ad, path, policy, dug, walked)
        if last["ok"] or last.get("error_code") != "BLOCKED":
            return last
        ad.map.invalidate()
    return last


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
    if hasattr(ad.map, "mark"):
        ad.map.mark(target, "solid", _nei(item), source="place")
        ad.map.flush()
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
    data = {"pos": list(ad.pose.pos), "facing": ad.pose.facing, "inventory": inventory}
    if ad.pose.source == "waypoint":
        data["pose_source"] = "waypoint"
    return ok(message, data)


async def verify_blocks(ad, expected: list[dict], page: int = 0) -> dict:
    if not ad.map.available:
        return err("UNSUPPORTED", NO_MAP)
    start = int(page) * VERIFY_PAGE
    chunk = expected[start:start + VERIFY_PAGE]
    missing, wrong = ad.map.verify(chunk)
    unverified = [{"pos": list(e["pos"]), "item": _nei(e["item"])} for e in getattr(ad.map, "last_unverified", [])]
    missing = [{"pos": list(e["pos"]), "item": _nei(e["item"])} for e in missing]
    wrong = [{"pos": list(e["pos"]), "item": _nei(e["item"])} for e in wrong]
    nxt = int(page) + 1 if start + VERIFY_PAGE < len(expected) else None
    data = {"checked": len(chunk), "missing": missing, "wrong": wrong, "next_page": nxt}
    if unverified:
        data["unverified"] = unverified
    return ok(f"Checked {len(chunk)}: {len(missing)} missing, {len(wrong)} wrong.", data)


async def search_docs(ad, query: str, mod: str | None = None, limit: int = 5) -> dict:
    return err("UNSUPPORTED", "no documentation service")


def scan_box(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> tuple[Pos, Pos]:
    lo = (min(x1, x2), min(y1, y2), min(z1, z2))
    hi = (max(x1, x2), max(y1, y2), max(z1, z2))
    return lo, hi


def scan_volume(lo: Pos, hi: Pos) -> int:
    return (hi[0] - lo[0] + 1) * (hi[1] - lo[1] + 1) * (hi[2] - lo[2] + 1)


def scan_chunks(lo: Pos, hi: Pos) -> list[tuple[Pos, Pos]]:
    out = []
    for y in range(lo[1], hi[1] + 1, SCAN_CHUNK):
        for z in range(lo[2], hi[2] + 1, SCAN_CHUNK):
            for x in range(lo[0], hi[0] + 1, SCAN_CHUNK):
                out.append(((x, y, z), (min(x + SCAN_CHUNK - 1, hi[0]), min(y + SCAN_CHUNK - 1, hi[1]),
                                        min(z + SCAN_CHUNK - 1, hi[2]))))
    return out


def scan_in_range(pos: Pos, lo: Pos, hi: Pos) -> bool:
    return all(-SCAN_RANGE <= lo[i] - pos[i] and hi[i] - pos[i] <= SCAN_RANGE for i in range(3))


def scan_message(scanned: int, solid: int, skipped: int, failed: int) -> str:
    text = f"Scanned {scanned} cells: {solid} not air."
    if skipped:
        text += f" {skipped} chunks out of geolyzer range ({SCAN_RANGE} blocks), move closer and scan again."
    if failed:
        text += f" {failed} chunks failed."
    return text


def _relative_box(ad, lo: Pos, hi: Pos) -> dict:
    from adapter.explored_map import geo_axes

    right, forward = geo_axes(ad.pose, True)
    pos = ad.pose.pos
    corners = [(x - pos[0], z - pos[2]) for x in (lo[0], hi[0]) for z in (lo[2], hi[2])]
    a = [wx * right[0] + wz * right[2] for wx, wz in corners]
    b = [wx * forward[0] + wz * forward[2] for wx, wz in corners]
    return {"x": min(a), "z": min(b), "y": lo[1] - pos[1], "width": max(a) - min(a) + 1,
            "depth": max(b) - min(b) + 1, "height": hi[1] - lo[1] + 1}


async def scan_area(ad, x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> dict:
    from adapter.explored_map import geo_cells

    lo, hi = scan_box(x1, y1, z1, x2, y2, z2)
    if scan_volume(lo, hi) > SCAN_MAX:
        return err("BLOCKED", f"box has {scan_volume(lo, hi)} cells, scan_area takes at most {SCAN_MAX}: "
                              "split it into smaller boxes")
    if (problem := await _missing(ad, need_map=False)) is not None:
        return problem
    pos = ad.pose.pos
    solid: dict[Pos, float] = {}
    scanned, failed, skipped = 0, 0, []
    for c_lo, c_hi in scan_chunks(lo, hi):
        if not scan_in_range(pos, c_lo, c_hi):
            skipped.append([*c_lo, *c_hi])
            continue
        env = await ad.raw("geo_scan", _relative_box(ad, c_lo, c_hi))
        if not env["ok"]:
            failed += 1
            continue
        scanned += scan_volume(c_lo, c_hi)
        for cell, value in geo_cells(ad.pose, env["message"]):
            if value != 0 and cell != pos and all(c_lo[i] <= cell[i] <= c_hi[i] for i in range(3)):
                solid[cell] = value
    cells = [[*p, v] for p, v in sorted(solid.items())]
    data = {"solid": cells, "scanned": scanned, "skipped": skipped, "failed": failed}
    return ok(scan_message(scanned, len(cells), len(skipped), failed), data)


ADDITIONS = {
    "face": face,
    "move_to": move_to,
    "place_at": place_at,
    "get_status": get_status,
    "verify_blocks": verify_blocks,
    "search_docs": search_docs,
    "scan_area": scan_area,
}
