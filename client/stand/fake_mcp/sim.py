"""Модель робота fake-MCP: состояние, движение, действия в мире.

Мир меняют только fake-MCP и подготовка сцены, поэтому карта занятости occ
совпадает с настоящим миром региона. По ней работают зрение и поиск пути.
Истиной для судьи остаётся сам мир.

Упрощения относительно настоящего робота OpenComputers: робот перемещается
мгновенно и может висеть в воздухе (OC позволяет подняться только невысоко),
опора у ставящихся блоков не нужна, гравитации нет.

Каждый метод с именем tool из контракта возвращает конверт envelope.ok/err.
"""

from __future__ import annotations

import math

from stand.fake_mcp.envelope import err, ok
from stand.fake_mcp.inventory import Container, Inventory
from stand.fake_mcp.pathfinding import NEIGHBOURS, astar
from stand.knowledge import Knowledge, normalize_id
from stand.scenario import Scenario
from stand.world.backend import WorldBackend
from stand.world.blocks import AIR, Block, Pos, baseline_block, format_block, parse_block
from stand.world.snapshot import Box

ENERGY_PER_STEP = 0.0005
ENERGY_PER_ACTION = 0.001
DIG_COST = 5.0
SCAN_PAGE = 100
VERIFY_PAGE = 50
CRAFTING = {"crafting_shaped", "crafting_shapeless"}
UNBREAKABLE = {"minecraft:bedrock"}

FACINGS = ("north", "east", "south", "west")
DIRS: dict[str, Pos] = {
    "north": (0, 0, -1),
    "south": (0, 0, 1),
    "east": (1, 0, 0),
    "west": (-1, 0, 0),
    "up": (0, 1, 0),
    "down": (0, -1, 0),
}

# Коды ошибок, которые может вернуть fake-MCP. Тест сверяет их с контрактом.
USED_CODES = {
    "BLOCKED", "NO_PATH", "OUT_OF_RANGE", "NO_ITEM", "INVENTORY_FULL", "NO_ENERGY",
    "CANT_PLACE", "UNKNOWN_ITEM", "NO_RECIPE", "CONNECTION_LOST", "TIMEOUT",
}


def _add(a: Pos, b: Pos) -> Pos:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


class RobotSim:
    """Состояние робота и мира региона одного сценария."""

    def __init__(self, scenario: Scenario, knowledge: Knowledge, world: WorldBackend):
        self.scenario = scenario
        self.k = knowledge
        self.world = world
        self.region: Box = scenario.region
        self.pos: Pos = tuple(scenario.robot["pos"])
        self.facing: str = scenario.robot["facing"]
        self.energy: float = float(scenario.robot["energy"])
        self.tool: str | None = None
        self.inventory = Inventory()
        for it in scenario.robot["inventory"]:
            self.inventory.add(it["item"], it["count"])
        self.placed: set[Pos] = set()
        scene = scenario.scene_blocks()
        self.occ: dict[Pos, Block] = {}
        for p in self.region.iter():
            b = scene.get(p, baseline_block(p[1]))
            if b != AIR:
                self.occ[p] = b
        # Контейнеры: склад с материалами, пустые сундуки и машины сцены.
        self.containers: dict[Pos, Container] = {}
        for p, b in scene.items():
            self._maybe_container(p, b)
        wh = self.containers.setdefault(tuple(scenario.warehouse["pos"]), Container(27))
        for item, count in scenario.warehouse["items"].items():
            wh.add(item, count)

    # Вспомогательное

    def _free(self, p: Pos) -> bool:
        return self.region.contains(p) and p not in self.occ

    def _side_dir(self, side: str) -> Pos | None:
        if side in ("up", "down"):
            return DIRS[side]
        i = FACINGS.index(self.facing)
        turn = {"front": 0, "right": 1, "back": 2, "left": 3}.get(side)
        if turn is None:
            return None
        return DIRS[FACINGS[(i + turn) % 4]]

    def _block_at(self, p: Pos) -> Block:
        if self.region.contains(p):
            return self.occ.get(p, AIR)
        return baseline_block(p[1])

    def _item_of(self, b: Block) -> str:
        return self.k.item_for(b) or format_block(b)

    def _spend(self, steps: int = 0, actions: int = 0) -> bool:
        need = steps * ENERGY_PER_STEP + actions * ENERGY_PER_ACTION
        if self.energy + 1e-12 < need:
            return False
        self.energy = max(0.0, self.energy - need)
        return True

    def _path(self, start: Pos, goal: Pos, policy: str) -> list[Pos] | None:
        def cost(p: Pos):
            if not self.region.contains(p):
                return None
            b = self.occ.get(p)
            if b is None:
                return 1.0
            if policy == "dig_through" and b[0] not in UNBREAKABLE:
                return DIG_COST
            return None

        return astar(start, goal, cost)

    def _maybe_container(self, p: Pos, b: Block) -> None:
        item = self.k.item_for(b)
        slots = self.k.container_slots(item) if item else 0
        if slots:
            self.containers[p] = Container(slots)

    def _break(self, p: Pos) -> Block:
        b = self.occ.pop(p)
        self.world.set_block(p, AIR)
        self.placed.discard(p)
        # Содержимое сломанного контейнера пропадает (в мире оно бы выпало).
        self.containers.pop(p, None)
        self.inventory.add(self._item_of(b), 1)
        return b

    def _face_towards(self, target: Pos) -> str:
        d = (target[0] - self.pos[0], target[1] - self.pos[1], target[2] - self.pos[2])
        for name in FACINGS:
            if DIRS[name] == d:
                self.facing = name
                return "front"
        return "up" if d[1] > 0 else "down"

    def _put_block(self, target: Pos, item: str, block: Block) -> None:
        self.world.set_block(target, block)
        self.occ[target] = block
        self.placed.add(target)
        self.inventory.remove(item, 1)
        self._maybe_container(target, block)

    def _placeable(self, item: str):
        """Проверки предмета перед установкой. Возвращает (item, block) или конверт ошибки."""
        item = normalize_id(item)
        if self.k.get_item(item) is None:
            return err("UNKNOWN_ITEM", f"unknown item {item}")
        if self.inventory.count(item) == 0:
            return err("NO_ITEM", f"no {item} in inventory")
        block = self.k.block_for(item)
        if block is None:
            return err("CANT_PLACE", f"{item} is not a placeable block")
        return item, block

    # Состояние и зрение

    def get_status(self) -> dict:
        wh = self.scenario.warehouse
        tool = {"item": self.tool, "durability": 1.0} if self.tool else None
        return ok("status", {
            "pos": list(self.pos),
            "facing": self.facing,
            "energy": round(self.energy, 4),
            "tool": tool,
            "inventory": self.inventory.summary(),
            "warehouse": {"pos": list(wh["pos"]), "side": wh["side"]},
        })

    def inspect(self, side: str) -> dict:
        d = self._side_dir(side)
        if d is None:
            return err("BLOCKED", f"unknown side {side}")
        b = self._block_at(_add(self.pos, d))
        if b == AIR:
            return ok("air", {"item": "minecraft:air"})
        item = self._item_of(b)
        info = self.k.get_item(item)
        return ok("block", {"item": item, "name": info["name"] if info else b[0]})

    def _box(self, box: dict) -> Box | None:
        try:
            b = Box(tuple(box["from"]), tuple(box["to"]))
        except (KeyError, TypeError):
            return None
        if not (self.region.contains(b.lo) and self.region.contains(b.hi)):
            return None
        return b

    def scan_area(self, box: dict, detail: str = "summary", page: int = 0) -> dict:
        b = self._box(box)
        if b is None:
            return err("OUT_OF_RANGE", "box must be inside the allowed area", {"area": self.region.to_json()})
        cells = list(b.iter())
        solid = [(p, self.occ[p]) for p in cells if p in self.occ]
        if detail != "full":
            counts: dict[str, int] = {}
            for _, blk in solid:
                item = self._item_of(blk)
                counts[item] = counts.get(item, 0) + 1
            top = dict(sorted(counts.items(), key=lambda t: (-t[1], t[0]))[:10])
            return ok("scanned", {
                "cells": len(cells), "air": len(cells) - len(solid), "solid": len(solid),
                "liquid": 0, "blocks": top,
            })
        start = page * SCAN_PAGE
        chunk = solid[start:start + SCAN_PAGE]
        nxt = page + 1 if start + SCAN_PAGE < len(solid) else None
        return ok("scanned", {
            "blocks": [{"pos": list(p), "item": self._item_of(blk)} for p, blk in chunk],
            "page": page,
            "next_page": nxt,
        })

    def get_known_map(self, box: dict, page: int = 0) -> dict:
        # Fake-MCP знает весь регион, поэтому карта совпадает с полным сканом.
        return self.scan_area(box, "full", page)

    # Движение

    def move_to(self, x: int, y: int, z: int, policy: str = "avoid") -> dict:
        target = (int(x), int(y), int(z))
        if not self.region.contains(target):
            return err("OUT_OF_RANGE", f"{list(target)} is outside the allowed area", {"area": self.region.to_json()})
        if policy not in ("avoid", "dig_through"):
            return err("BLOCKED", f"unknown policy {policy}")
        if target in self.occ and policy == "avoid":
            return err("BLOCKED", f"{list(target)} is occupied by {self._item_of(self.occ[target])}")
        path = self._path(self.pos, target, policy)
        if path is None:
            return err("NO_PATH", f"no route to {list(target)} with policy {policy}", {"from": list(self.pos)})
        to_dig = [p for p in path[1:] if p in self.occ]
        steps = len(path) - 1
        if not self._spend(steps=steps, actions=len(to_dig)):
            return err("NO_ENERGY", "not enough energy for this move", {"energy": round(self.energy, 4)})
        for p in to_dig:
            # Если инвентарь полон, добытый блок пропадает, как выпавший предмет.
            self._break(p)
        dug = [list(p) for p in to_dig]
        self.pos = target
        return ok("moved", {"pos": list(self.pos), "steps": steps, "dug": dug})

    def move(self, dir: str, n: int = 1) -> dict:
        if dir in ("up", "down"):
            d = DIRS[dir]
        elif dir in ("forward", "back"):
            d = self._side_dir("front" if dir == "forward" else "back")
        else:
            return err("BLOCKED", f"unknown direction {dir}")
        moved = 0
        for _ in range(int(n)):
            nxt = _add(self.pos, d)
            if not self.region.contains(nxt):
                return err("OUT_OF_RANGE", "next step leaves the allowed area", {"moved": moved, "pos": list(self.pos)})
            if nxt in self.occ:
                return err("BLOCKED", f"{list(nxt)} is occupied", {"moved": moved, "pos": list(self.pos)})
            if not self._spend(steps=1):
                return err("NO_ENERGY", "not enough energy", {"moved": moved, "pos": list(self.pos)})
            self.pos = nxt
            moved += 1
        return ok("moved", {"moved": moved, "pos": list(self.pos)})

    def face(self, dir: str) -> dict:
        if dir not in FACINGS:
            return err("BLOCKED", f"unknown direction {dir}")
        self.facing = dir
        return ok("turned", {"facing": dir})

    # Мир

    def dig(self, side: str) -> dict:
        d = self._side_dir(side)
        if d is None:
            return err("BLOCKED", f"unknown side {side}")
        target = _add(self.pos, d)
        if not self.region.contains(target):
            return err("OUT_OF_RANGE", f"{list(target)} is outside the allowed area")
        b = self.occ.get(target)
        if b is None:
            return err("BLOCKED", f"nothing to dig at {list(target)}")
        if b[0] in UNBREAKABLE:
            return err("BLOCKED", f"{b[0]} cannot be broken")
        if self.inventory.space_for(self._item_of(b)) < 1:
            return err("INVENTORY_FULL", "no free slot for the dug block")
        if not self._spend(actions=1):
            return err("NO_ENERGY", "not enough energy")
        self._break(target)
        return ok("dug", {"pos": list(target), "item": self._item_of(b)})

    def place(self, item: str, side: str) -> dict:
        d = self._side_dir(side)
        if d is None:
            return err("BLOCKED", f"unknown side {side}")
        checked = self._placeable(item)
        if isinstance(checked, dict):
            return checked
        item, block = checked
        target = _add(self.pos, d)
        if not self.region.contains(target):
            return err("OUT_OF_RANGE", f"{list(target)} is outside the allowed area")
        if target in self.occ:
            return err("CANT_PLACE", f"{list(target)} is occupied by {self._item_of(self.occ[target])}")
        if not self._spend(actions=1):
            return err("NO_ENERGY", "not enough energy")
        self._put_block(target, item, block)
        return ok("placed", {"pos": list(target), "item": item})

    def place_at(self, x: int, y: int, z: int, item: str, from_: str | None = None) -> dict:
        target = (int(x), int(y), int(z))
        checked = self._placeable(item)
        if isinstance(checked, dict):
            return checked
        item, block = checked
        if not self.region.contains(target):
            return err("OUT_OF_RANGE", f"{list(target)} is outside the allowed area", {"area": self.region.to_json()})
        if target in self.occ:
            return err("CANT_PLACE", f"{list(target)} is occupied by {self._item_of(self.occ[target])}")
        if from_ is not None:
            if from_ not in DIRS:
                return err("BLOCKED", f"unknown approach side {from_}")
            approaches = [_add(target, DIRS[from_])]
        else:
            approaches = [_add(target, d) for d in NEIGHBOURS]
        best = None
        for a in approaches:
            if not self._free(a):
                continue
            path = self._path(self.pos, a, "avoid")
            if path is not None and (best is None or len(path) < len(best)):
                best = path
        if best is None:
            return err("NO_PATH", f"no free approach to {list(target)}", {"from": list(self.pos)})
        steps = len(best) - 1
        if not self._spend(steps=steps, actions=1):
            return err("NO_ENERGY", "not enough energy", {"energy": round(self.energy, 4)})
        self.pos = best[-1]
        self._face_towards(target)
        self._put_block(target, item, block)
        return ok("placed", {"pos": list(target), "item": item, "robot": list(self.pos), "steps": steps})

    def use(self, side: str, item: str | None = None) -> dict:
        # В первой версии без эффекта: действие только попадает в action log.
        if self._side_dir(side) is None:
            return err("BLOCKED", f"unknown side {side}")
        return ok("used", {"side": side, "item": item})

    # Инвентарь и контейнеры

    def _container(self, side: str):
        d = self._side_dir(side)
        if d is None:
            return err("BLOCKED", f"unknown side {side}")
        p = _add(self.pos, d)
        c = self.containers.get(p)
        if c is None:
            return err("BLOCKED", f"no container on {side}")
        return p, c

    def _known(self, item: str):
        item = normalize_id(item)
        if self.k.get_item(item) is None:
            return err("UNKNOWN_ITEM", f"unknown item {item}")
        return item

    def list_inventory(self, detail: str = "summary") -> dict:
        if detail == "full":
            return ok("inventory", {"slots": [v for v in self.inventory.slots_view() if v["item"]],
                                    "total": self.inventory.size})
        return ok("inventory", self.inventory.summary())

    def inspect_container(self, side: str) -> dict:
        found = self._container(side)
        if isinstance(found, dict):
            return found
        p, c = found
        return ok("container", {"block": self._item_of(self.occ.get(p, AIR)), "size": c.size,
                                "slots": c.nonempty_view()})

    def take(self, side: str, item: str, count: int, slot: int | None = None) -> dict:
        found = self._container(side)
        if isinstance(found, dict):
            return found
        _, c = found
        item = self._known(item)
        if isinstance(item, dict):
            return item
        count = int(count)
        if slot is not None and not c.has_slot(slot):
            return err("BLOCKED", f"container has no slot {slot}")
        available = c.slot_count(slot, item) if slot is not None else c.count(item)
        if available < count:
            return err("NO_ITEM", f"container has {available} of {item}", {"available": available})
        if self.inventory.space_for(item) < count:
            return err("INVENTORY_FULL", "not enough free space in the robot inventory")
        if not self._spend(actions=1):
            return err("NO_ENERGY", "not enough energy")
        if slot is not None:
            c.take_slot(slot, item, count)
        else:
            c.remove(item, count)
        self.inventory.add(item, count)
        return ok("taken", {"moved": count})

    def put(self, side: str, item: str, count: int, slot: int | None = None) -> dict:
        found = self._container(side)
        if isinstance(found, dict):
            return found
        _, c = found
        item = self._known(item)
        if isinstance(item, dict):
            return item
        count = int(count)
        if self.inventory.count(item) < count:
            return err("NO_ITEM", f"robot has {self.inventory.count(item)} of {item}")
        if slot is not None and not c.has_slot(slot):
            return err("BLOCKED", f"container has no slot {slot}")
        space = c.slot_space(slot, item) if slot is not None else c.space_for(item)
        if space < count:
            return err("INVENTORY_FULL", f"container has room for {space}")
        if not self._spend(actions=1):
            return err("NO_ENERGY", "not enough energy")
        self.inventory.remove(item, count)
        if slot is not None:
            c.put_slot(slot, item, count)
        else:
            c.add(item, count)
        return ok("put", {"moved": count})

    def equip(self, item: str) -> dict:
        item = self._known(item)
        if isinstance(item, dict):
            return item
        if not self.inventory.remove(item, 1):
            return err("NO_ITEM", f"no {item} in inventory")
        if self.tool:
            self.inventory.add(self.tool, 1)
        self.tool = item
        return ok("equipped", {"tool": item})

    def drop(self, item: str, count: int) -> dict:
        item = self._known(item)
        if isinstance(item, dict):
            return item
        if not self.inventory.remove(item, int(count)):
            return err("NO_ITEM", f"robot has {self.inventory.count(item)} of {item}")
        return ok("dropped", {"dropped": int(count)})

    # Крафт

    def craft(self, item: str, count: int) -> dict:
        item = self._known(item)
        if isinstance(item, dict):
            return item
        recipe = next((r for r in self.k.get_recipes(item) if r["type"] in CRAFTING), None)
        if recipe is None:
            return err("NO_RECIPE", f"no crafting recipe for {item}")
        out = recipe["output"]["count"]
        crafts = math.ceil(int(count) / out)
        need = {ing: per * crafts for ing, per in recipe["ingredients"].items()}
        missing = [
            {"item": ing, "count": n - self.inventory.count(ing)}
            for ing, n in need.items() if self.inventory.count(ing) < n
        ]
        if missing:
            return err("NO_ITEM", "not enough ingredients", {"missing": missing})
        if not self._need_action():
            return err("NO_ENERGY", "not enough energy")
        saved = [list(s) if s else None for s in self.inventory.slots]
        for ing, n in need.items():
            self.inventory.remove(ing, n)
        if self.inventory.add(item, crafts * out):
            self.inventory.slots = saved
            return err("INVENTORY_FULL", "no room for the crafted items")
        self._spend(actions=1)
        return ok("crafted", {"crafted": crafts * out, "item": item})

    def _need_action(self) -> bool:
        return self.energy + 1e-12 >= ENERGY_PER_ACTION

    # Знания

    def search_items(self, query: str, limit: int = 10) -> dict:
        return ok("items", {"items": self.k.search_items(query, int(limit))})

    def get_item(self, id: str) -> dict:
        card = self.k.get_item(id)
        if card is None:
            return err("UNKNOWN_ITEM", f"unknown item {id}")
        return ok("item", card)

    def get_recipes(self, item: str) -> dict:
        known = self._known(item)
        if isinstance(known, dict):
            return known
        recipes = []
        for r in self.k.get_recipes(known):
            entry = {"type": r["type"], "output": r["output"], "ingredients": r["ingredients"]}
            for key in ("grid", "machine"):
                if key in r:
                    entry[key] = r[key]
            recipes.append(entry)
        return ok("recipes", {"recipes": recipes})

    def plan_materials(self, item: str, count: int, use_inventory: bool = True) -> dict:
        known = self._known(item)
        if isinstance(known, dict):
            return known
        have: dict[str, int] = {}
        if use_inventory:
            for src in (self.inventory, self.containers.get(tuple(self.scenario.warehouse["pos"]))):
                if src is None:
                    continue
                for it, n in src.totals().items():
                    have[it] = have.get(it, 0) + n
        plan = self.k.plan_materials(known, int(count), have)
        return ok("plan", {"tree": plan["tree"], "missing": plan["missing"]})

    def search_docs(self, query: str, mod: str | None = None, limit: int = 5) -> dict:
        return ok("docs", {"docs": self.k.search_docs(query, mod, int(limit))})

    # Проверка

    def verify_blocks(self, expected: list[dict], page: int = 0) -> dict:
        start = int(page) * VERIFY_PAGE
        chunk = expected[start:start + VERIFY_PAGE]
        missing, wrong = [], []
        for e in chunk:
            p = tuple(e["pos"])
            item = normalize_id(e["item"])
            block = AIR if item == AIR[0] else (self.k.block_for(item) or parse_block(item))
            any_meta = self.k.meta_mask(block[0]) != 15
            if self.world.test_block(p, block, any_meta=any_meta):
                continue
            entry = {"pos": list(p), "item": item}
            (missing if self.world.test_block(p, AIR) else wrong).append(entry)
        nxt = int(page) + 1 if start + VERIFY_PAGE < len(expected) else None
        return ok("verified", {"checked": len(chunk), "missing": missing, "wrong": wrong, "next_page": nxt})

    def read_block_info(self, side: str) -> dict:
        return err("BLOCKED", "functional check is not supported by the fake MCP (read_block_info)")

    # Служебные

    def stop(self) -> dict:
        return ok("stopped")
