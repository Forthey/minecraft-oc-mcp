"""Модель робота fake-MCP v2: состояние, примитивы oc-mcp, мир региона.

Мир меняют только fake-MCP и подготовка сцены, поэтому карта занятости occ
совпадает с настоящим миром региона. По ней работают зрение и поиск пути.
Истиной для судьи остаётся сам мир.

Робот устроен как в oc-mcp: инвентарь из 16 слотов (с 1), выбранный слот, слот
инструмента и направление. Стороны front, up и down считаются от направления.
Тексты ответов берутся из texts.py, это строки из Lua-кода oc-mcp.

Упрощения относительно настоящего робота OpenComputers: робот перемещается
мгновенно и может висеть в воздухе, опора у ставящихся блоков не нужна,
гравитации нет, use ничего не делает.

Каждый метод с именем tool из контракта возвращает конверт envelope.ok/err.
"""

from __future__ import annotations

import json
from collections import Counter

from stand.fake_mcp import texts
from stand.fake_mcp.additions import Additions
from stand.fake_mcp.envelope import err, ok
from stand.fake_mcp.geometry import DIRS, FACINGS, add as _add, scale as _scale
from stand.fake_mcp.inventory import Container, Inventory
from stand.fake_mcp.nei import CRAFT_GRID, FakeNei, NeiError, nei_id
from adapter.pathfinding import astar
from stand.knowledge import Knowledge, normalize_id
from stand.scenario import Scenario
from stand.world.backend import WorldBackend
from stand.world.blocks import AIR, Block, Pos, baseline_block, format_block, parse_block
from stand.world.snapshot import Box

ENERGY_PER_STEP = 0.0005
ENERGY_PER_ACTION = 0.001
DIG_COST = 5.0
UNBREAKABLE = {"minecraft:bedrock"}
GEO_SCAN_MAX = 64
DEFAULT_HARDNESS = 1.5

TURNS = {"right": 1, "around": 2, "left": 3}
SIDE_TURNS = {"front": 0, "right": 1, "back": 2, "left": 3}
SURROUNDINGS = ("front", "back", "left", "right", "up", "down")
STACK = 64
# Коды OC NEI Bridge и их коды в нашем контракте.
NEI_CODES = {"UNKNOWN_ITEM": "UNKNOWN_ITEM", "UNKNOWN_RECIPE": "NO_RECIPE", "NO_PROVIDER": "NO_PROVIDER",
             "NO_INVENTORY": "BLOCKED"}

# Коды ошибок, которые может вернуть fake-MCP. Тест сверяет их с контрактом.
USED_CODES = {
    "BLOCKED", "NO_PATH", "OUT_OF_RANGE", "NO_ITEM", "INVENTORY_FULL", "NO_ENERGY", "TOOL_BROKEN",
    "CANT_PLACE", "UNKNOWN_ITEM", "NO_RECIPE", "CONNECTION_LOST", "TIMEOUT", "NO_PROVIDER",
}


class RobotSim(Additions):
    """Состояние робота и мира региона одного сценария."""

    def __init__(self, scenario: Scenario, knowledge: Knowledge, world: WorldBackend):
        self.scenario = scenario
        self.k = knowledge
        self.nei = FakeNei(knowledge)
        self.world = world
        self.region: Box = scenario.region
        self.pos: Pos = tuple(scenario.robot["pos"])
        self.facing: str = scenario.robot["facing"]
        self.energy: float = float(scenario.robot["energy"])
        self.selected = 1
        self.tool: str | None = None
        self.tool_count = 0
        self.inventory = Inventory()
        for it in scenario.robot["inventory"]:
            self.inventory.add(normalize_id(it["item"]), it["count"])
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
            wh.add(normalize_id(item), count)

    # Вспомогательное

    def _free(self, p: Pos) -> bool:
        return self.region.contains(p) and p not in self.occ

    def _side_dir(self, side: str) -> Pos | None:
        if side in ("up", "down"):
            return DIRS[side]
        turn = SIDE_TURNS.get(side)
        if turn is None:
            return None
        return DIRS[FACINGS[(FACINGS.index(self.facing) + turn) % 4]]

    def side_pos(self, side: str) -> Pos | None:
        """Клетка на стороне робота (front, back, left, right, up, down)."""
        d = self._side_dir(side)
        return None if d is None else _add(self.pos, d)

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
        """Ломает блок, добыча идёт в инвентарь. Если места нет, она пропадает (выпала бы в мир)."""
        b = self.occ.pop(p)
        self.world.set_block(p, AIR)
        self.placed.discard(p)
        # Содержимое сломанного контейнера пропадает (в мире оно бы выпало).
        self.containers.pop(p, None)
        self.inventory.add(self._item_of(b), 1)
        return b

    def _put_block(self, target: Pos, block: Block) -> None:
        self.world.set_block(target, block)
        self.occ[target] = block
        self.placed.add(target)
        self._maybe_container(target, block)

    def _hardness(self, b: Block) -> float:
        if b == AIR:
            return 0.0
        if b[0] in UNBREAKABLE:
            return -1.0
        item = self.k.items.get(self._item_of(b))
        return float(item.get("hardness", DEFAULT_HARDNESS)) if item else DEFAULT_HARDNESS

    def _bad_slot(self, *slots) -> int | None:
        """Первый слот робота вне 1..size или None. Проверяется до любых изменений."""
        for s in slots:
            if s is not None and not 1 <= int(s) <= self.inventory.size:
                return int(s)
        return None

    def _tool_text(self) -> str:
        return f"tool {self.tool}" if self.tool else texts.NO_TOOL

    # Движение

    def move(self, direction: str, n: int = 1) -> dict:
        if direction in ("up", "down"):
            d = DIRS[direction]
        elif direction in ("forward", "back"):
            d = self._side_dir("front" if direction == "forward" else "back")
        else:
            return err("BLOCKED", f"unknown direction {direction}")
        n = int(n)
        for done in range(n):
            nxt = _add(self.pos, d)
            if not self._free(nxt):
                return err("BLOCKED", texts.moved_partial(done, n, direction), {"pos": list(self.pos), "facing": self.facing})
            if not self._spend(steps=1):
                return err("NO_ENERGY", texts.NO_ENERGY, {"pos": list(self.pos), "facing": self.facing})
            self.pos = nxt
        return ok(texts.moved(direction, n), {"pos": list(self.pos), "facing": self.facing})

    def turn(self, direction: str) -> dict:
        turn = TURNS.get(direction)
        if turn is None:
            return err("BLOCKED", f"turn failed: unknown direction {direction}")
        self.facing = FACINGS[(FACINGS.index(self.facing) + turn) % 4]
        return ok(texts.turned(direction), {"pos": list(self.pos), "facing": self.facing})

    # Мир

    def place(self, side: str = "front", slot: int | None = None, sneaky: bool = False) -> dict:
        slot = int(slot) if slot is not None else self.selected
        if self._bad_slot(slot) is not None:
            return err("BLOCKED", texts.place_failed(slot, side, "invalid slot"))
        target = self.side_pos(side)
        if target is None:
            return err("BLOCKED", texts.place_failed(slot, side, "unknown side"))
        content = self.inventory.slot(slot)
        if content is None:
            return err("NO_ITEM", texts.slot_empty(slot))
        item, count = content
        block = self.k.block_for(item)
        if block is None:
            return err("CANT_PLACE", texts.place_failed(slot, side, "item is not a block"))
        if not self.region.contains(target):
            return err("OUT_OF_RANGE", texts.place_failed(slot, side, "outside the stand region"))
        if target in self.occ:
            return err("BLOCKED", texts.place_occupied(slot, side, format_block(self.occ[target])))
        if not self._spend(actions=1):
            return err("NO_ENERGY", texts.NO_ENERGY)
        self._put_block(target, block)
        self.inventory.set_slot(slot, item, count - 1)
        return ok(texts.placed(slot, side, format_block(block), count - 1), {"pos": list(target)})

    def swing(self, side: str = "front", sneaky: bool = False) -> dict:
        target = self.side_pos(side)
        if target is None:
            return err("BLOCKED", texts.swing_failed(side, "unknown side"))
        if not self.region.contains(target):
            return err("OUT_OF_RANGE", texts.swing_failed(side, "outside the stand region"))
        b = self.occ.get(target)
        if b is None:
            return err("BLOCKED", texts.swing_air(side))
        name = format_block(b)
        if b[0] in UNBREAKABLE:
            return err("TOOL_BROKEN", texts.swing_cannot_break(name, side, self._tool_text()))
        if not self._spend(actions=1):
            return err("NO_ENERGY", texts.NO_ENERGY)
        self._break(target)
        return ok(texts.broke(name, side, self._tool_text()), {"pos": list(target)})

    def use(self, side: str = "front", sneaky: bool = False, duration: float | None = None) -> dict:
        # Без эффекта: действие только попадает в action log.
        if self.side_pos(side) is None:
            return err("BLOCKED", f"use {side} failed: unknown side")
        return ok(texts.used(side))

    # Зрение

    def surroundings(self) -> dict:
        sides = {}
        lines = []
        for side in SURROUNDINGS:
            b = self._block_at(self.side_pos(side))
            kind = "air" if b == AIR else "solid"
            sides[side] = {"block": format_block(b), "kind": kind}
            lines.append(f"{side}: {format_block(b)} ({kind})")
        return ok("\n".join(lines))

    def geo_scan(self, x: int = -4, z: int = -4, y: int = 0, width: int = 8, depth: int = 8,
                 height: int = 1) -> dict:
        """Твёрдость блоков бокса в осях робота: x вправо, z вперёд, y вверх.

        data.hardness индексируется [dy][dz][dx]. Шума, как у настоящего геолайзера, нет.
        """
        if width * depth * height > GEO_SCAN_MAX:
            return err("BLOCKED", texts.GEO_SCAN_TOO_BIG)
        right, forward = self._side_dir("right"), self._side_dir("front")
        layers = []
        for dy in range(height):
            rows = []
            for dz in range(depth):
                row = []
                for dx in range(width):
                    p = _add(_add(_add(self.pos, _scale(right, x + dx)), _scale(forward, z + dz)), (0, y + dy, 0))
                    row.append(self._hardness(self._block_at(p)))
                rows.append(row)
            layers.append(rows)
        lines = ["axes: x = right, z = forward, y = up"]
        for dy, rows in enumerate(layers):
            lines.append(f"y={y + dy} (rows z={z}..{z + depth - 1}, columns x={x}..{x + width - 1}):")
            lines.extend(" ".join("." if v == 0 else f"{v:g}" for v in row) for row in rows)
        return ok("\n".join(lines))

    def world_info(self) -> dict:
        info = {"robot_id": "fake-robot", "robot_name": "robot", "x": self.pos[0], "y": self.pos[1],
                "z": self.pos[2], "facing": self.facing, "world_id": "stand"}
        return ok(json.dumps(info, sort_keys=True), info)

    # Инвентарь и хранилища

    def _slot_lines(self, slots: list[tuple[int, str, int]]) -> tuple[list[str], list[dict]]:
        lines, data = [], []
        for slot, item, count in slots:
            name, label = nei_id(item), self.nei.label(item)
            lines.append(texts.item_line(slot, count, name, label))
            data.append({"slot": slot, "count": count, "name": name, "label": label})
        return lines, data

    def _robot_slots(self) -> list[tuple[int, str, int]]:
        return [(i, *self.inventory.slot(i)) for i in range(1, self.inventory.size + 1) if self.inventory.slot(i)]

    def _storage(self, side: str) -> tuple[Pos, Container] | None:
        p = self.side_pos(side)
        c = self.containers.get(p) if p is not None else None
        return (p, c) if c is not None else None

    def inventory_scan(self) -> dict:
        lines, data = self._slot_lines(self._robot_slots())
        return ok("\n".join(lines) or texts.INVENTORY_EMPTY, {"slots": data})

    def storage_scan(self, side: str = "front") -> dict:
        found = self._storage(side)
        if found is None:
            p = self.side_pos(side)
            b = self._block_at(p) if p is not None else AIR
            header = f"Block: {format_block(b)}\n" if b != AIR else ""
            return err("BLOCKED", header + texts.no_storage(side))
        p, c = found
        block = format_block(self.occ.get(p, AIR))
        lines, data = self._slot_lines([(i + 1, s[0], s[1]) for i, s in enumerate(c.slots) if s])
        message = texts.storage_header(block, c.size) + "\n" + ("\n".join(lines) or texts.STORAGE_EMPTY)
        return ok(message, {"block": block, "size": c.size, "slots": data})

    def storage_take(self, side: str, slot: int, count: int | None = None, robot_slot: int | None = None) -> dict:
        slot = int(slot)
        if self._bad_slot(robot_slot) is not None:
            return err("BLOCKED", texts.take_failed(side, slot, f"invalid slot {robot_slot}"))
        found = self._storage(side)
        if found is None:
            return err("BLOCKED", texts.take_failed(side, slot, "no inventory"))
        _, c = found
        content = c.slots[slot - 1] if 1 <= slot <= c.size else None
        if not content:
            return err("NO_ITEM", texts.take_failed(side, slot, "slot is empty"))
        item, have = content
        want = min(have, int(count)) if count is not None else have
        if robot_slot is not None:
            target = self.inventory.slot(int(robot_slot))
            if target and target[0] != item:
                return err("BLOCKED", texts.take_failed(side, slot, "target slot holds another item"))
            room = STACK - (target[1] if target else 0)
        else:
            room = self.inventory.space_for(item)
        n = min(want, room)
        if n <= 0:
            return err("INVENTORY_FULL", texts.take_failed(side, slot, "robot inventory is full"))
        if not self._spend(actions=1):
            return err("NO_ENERGY", texts.NO_ENERGY)
        c.take_slot(slot - 1, item, n)
        if robot_slot is not None:
            target = self.inventory.slot(int(robot_slot))
            self.inventory.set_slot(int(robot_slot), item, (target[1] if target else 0) + n)
        else:
            self.inventory.add(item, n)
        return ok(texts.took(side, slot))

    def storage_put(self, side: str, robot_slot: int, count: int | None = None, slot: int | None = None) -> dict:
        robot_slot = int(robot_slot)
        if self._bad_slot(robot_slot) is not None:
            return err("BLOCKED", texts.put_failed(side, f"invalid slot {robot_slot}"))
        found = self._storage(side)
        if found is None:
            return err("BLOCKED", texts.put_failed(side, "no inventory"))
        _, c = found
        content = self.inventory.slot(robot_slot)
        if content is None:
            return err("NO_ITEM", texts.put_failed(side, f"robot slot {robot_slot} is empty"))
        item, have = content
        want = min(have, int(count)) if count is not None else have
        if slot is not None and not c.has_slot(int(slot) - 1):
            return err("BLOCKED", texts.put_failed(side, f"no slot {slot}"))
        room = c.slot_space(int(slot) - 1, item) if slot is not None else c.space_for(item)
        n = min(want, room)
        if n <= 0:
            return err("INVENTORY_FULL", texts.put_failed(side, "inventory full"))
        if not self._spend(actions=1):
            return err("NO_ENERGY", texts.NO_ENERGY)
        if slot is not None:
            c.put_slot(int(slot) - 1, item, n)
        else:
            c.add(item, n)
        self.inventory.set_slot(robot_slot, item, have - n)
        return ok(texts.put_done(robot_slot, side))

    def inventory_transfer(self, from_slot: int, to_slot: int, count: int | None = None) -> dict:
        a, b = int(from_slot), int(to_slot)
        bad = self._bad_slot(a, b)
        if bad is not None:
            return err("BLOCKED", texts.transfer_failed(a, b, f"invalid slot {bad}"))
        src, dst = self.inventory.slot(a), self.inventory.slot(b)
        if src is None:
            return err("NO_ITEM", texts.transfer_failed(a, b, f"slot {a} is empty"))
        if dst and dst[0] != src[0]:
            return err("BLOCKED", texts.transfer_failed(a, b, f"slot {b} holds a different item"))
        n = min(src[1] if count is None else int(count), src[1], STACK - (dst[1] if dst else 0))
        if n <= 0:
            return err("INVENTORY_FULL", texts.transfer_failed(a, b, f"slot {b} is full"))
        self.inventory.set_slot(a, src[0], src[1] - n)
        self.inventory.set_slot(b, src[0], (dst[1] if dst else 0) + n)
        return ok(texts.transferred(a, b))

    def equip(self, slot: int) -> dict:
        slot = int(slot)
        if self._bad_slot(slot) is not None:
            return err("BLOCKED", texts.equip_failed(slot) + ": invalid slot")
        content = self.inventory.slot(slot)
        if content is None:
            return err("NO_ITEM", texts.equip_failed(slot))
        old = (self.tool, self.tool_count) if self.tool else (None, 0)
        self.tool, self.tool_count = content
        self.inventory.set_slot(slot, old[0], old[1])
        return ok(texts.equipped(slot))

    # Крафт

    def _grid(self) -> dict[int, tuple[str, int]]:
        """Содержимое сетки: клетка 1-9 и (предмет, количество)."""
        out = {}
        for cell, slot in enumerate(CRAFT_GRID, start=1):
            content = self.inventory.slot(slot)
            if content:
                out[cell] = content
        return out

    def _grid_text(self, grid: dict[int, tuple[str, int]]) -> str:
        rows = []
        for row in range(3):
            cells = []
            for col in range(3):
                cell = row * 3 + col + 1
                c = grid.get(cell)
                cells.append(f"[{CRAFT_GRID[cell - 1]}: " + (f"{c[1]}x {c[0]}" if c else "empty") + "]")
            rows.append(" ".join(cells))
        return "\n".join(rows)

    def _match(self, grid: dict[int, tuple[str, int]]) -> dict | None:
        """Рецепт верстака, который совпадает с сеткой. Shaped сравнивается со сдвигом."""
        items = {cell: item for cell, (item, _) in grid.items()}

        def shape(cells: dict[tuple[int, int], str]) -> dict[tuple[int, int], str]:
            r0 = min(r for r, _ in cells)
            c0 = min(c for _, c in cells)
            return {(r - r0, c - c0): v for (r, c), v in cells.items()}

        mine = shape({divmod(cell - 1, 3): item for cell, item in items.items()})
        for r in self.k.recipes:
            if r["type"] == "crafting_shaped":
                theirs = {(i, j): normalize_id(v) for i, row in enumerate(r["grid"]) for j, v in enumerate(row) if v}
                if shape(theirs) == mine:
                    return r
            elif r["type"] == "crafting_shapeless":
                if Counter(items.values()) == Counter({i: n for i, n in r["ingredients"].items()}):
                    return r
        return None

    def _result_slot(self, item: str, n: int, wanted: int | None = None) -> int | None:
        """Слот вне сетки для результата: заданный или первый пустой либо с тем же предметом."""
        slots = [wanted] if wanted is not None else [i for i in range(1, self.inventory.size + 1) if i not in CRAFT_GRID]
        for i in slots:
            c = self.inventory.slot(i)
            if c is None or (c[0] == item and c[1] + n <= STACK):
                return i
        return None

    def craft(self, count: int | None = None, result_slot: int | None = None) -> dict:
        if self._bad_slot(result_slot) is not None:
            return err("BLOCKED", f"invalid slot {result_slot}")
        if result_slot is not None and int(result_slot) in CRAFT_GRID:
            return err("BLOCKED", f"result_slot {result_slot} is inside the crafting grid, use 4, 8, 12 or 13+")
        grid = self._grid()
        if not grid:
            return err("NO_ITEM", texts.GRID_EMPTY)
        recipe = self._match(grid)
        crafts = min(n for _, n in grid.values())
        if count is not None:
            crafts = min(crafts, int(count))
        out_item = recipe["output"]["item"] if recipe else None
        n = crafts * recipe["output"]["count"] if recipe else 0
        slot = self._result_slot(out_item, n, int(result_slot) if result_slot is not None else None) if recipe else None
        if recipe is None or slot is None:
            return err("NO_RECIPE", texts.no_grid_match(self._grid_text(grid)))
        if not self._spend(actions=1):
            return err("NO_ENERGY", texts.NO_ENERGY)
        for cell, (item, have) in grid.items():
            self.inventory.set_slot(CRAFT_GRID[cell - 1], item, have - crafts)
        have = self.inventory.slot(slot)
        self.inventory.set_slot(slot, out_item, (have[1] if have else 0) + n)
        return ok(texts.CRAFTED)

    def _nei_err(self, e: NeiError) -> dict:
        return err(NEI_CODES.get(e.code, "UNKNOWN"), str(e))

    def craft_recipe(self, recipe: str, count: int = 1) -> dict:
        count = int(count)
        try:
            full = self.nei.recipe(recipe)
        except NeiError as e:
            return self._nei_err(e)
        if full.get("overlay") != "crafting":
            return err("NO_RECIPE", texts.not_crafting_recipe(full["cat"]))
        for g in full["grid"]:
            if g["count"] * count > STACK:
                return err("BLOCKED", texts.count_too_large(g["robotSlot"], g["count"] * count))
        saved = [list(s) if s else None for s in self.inventory.slots]
        # Сетку освобождаем целиком: чужие предметы уходят в слоты вне сетки.
        for slot in CRAFT_GRID:
            content = self.inventory.slot(slot)
            if content is None:
                continue
            target = self._result_slot(content[0], content[1])
            if target is None:
                self.inventory.slots = saved
                return err("INVENTORY_FULL", texts.no_room_for_grid(slot))
            have = self.inventory.slot(target)
            self.inventory.set_slot(target, content[0], (have[1] if have else 0) + content[1])
            self.inventory.set_slot(slot, None, 0)
        missing = []
        for g in full["grid"]:
            item, need = normalize_id(g["item"]), g["count"] * count
            for i in range(1, self.inventory.size + 1):
                c = self.inventory.slot(i)
                if need == 0 or i in CRAFT_GRID or not c or c[0] != item:
                    continue
                n = min(need, c[1])
                self.inventory.set_slot(i, item, c[1] - n)
                cell = self.inventory.slot(g["robotSlot"])
                self.inventory.set_slot(g["robotSlot"], item, (cell[1] if cell else 0) + n)
                need -= n
            if need:
                missing.append(texts.missing_entry(need, self.nei.label(item), g["robotSlot"]))
        if missing:
            return err("NO_ITEM", texts.ingredients_missing(missing))
        out = full["out"][0]
        out_item, n = normalize_id(out["item"]), out["n"] * count
        slot = self._result_slot(out_item, n)
        if slot is None:
            return err("INVENTORY_FULL", texts.NO_RESULT_SLOT)
        if not self._spend(actions=1):
            return err("NO_ENERGY", texts.NO_ENERGY)
        for g in full["grid"]:
            cell = self.inventory.slot(g["robotSlot"])
            self.inventory.set_slot(g["robotSlot"], cell[0], cell[1] - g["count"] * count)
        have = self.inventory.slot(slot)
        total = (have[1] if have else 0) + n
        self.inventory.set_slot(slot, out_item, total)
        message = texts.crafted_recipe(count, slot, total, nei_id(out_item), self.nei.label(out_item))
        return ok(message)

    # Знания (NEI)

    def _nei(self, call) -> dict:
        try:
            result = call()
        except NeiError as e:
            return self._nei_err(e)
        return ok(json.dumps(result, sort_keys=True), result)

    def nei_find(self, text: str, limit: int | None = None, lang: str | None = None) -> dict:
        return self._nei(lambda: self.nei.find(text, limit))

    def nei_recipes(self, item: str, usages: bool = False, category: str | None = None, limit: int | None = None,
                    cursor: str | None = None, lang: str | None = None) -> dict:
        return self._nei(lambda: self.nei.recipes(item, usages, category, limit))

    def nei_recipe(self, recipe: str, lang: str | None = None) -> dict:
        return self._nei(lambda: self.nei.recipe(recipe))

    def nei_craft_tree(self, item: str, count: int = 1, use_inventory: bool = True, lang: str | None = None) -> dict:
        have = self.inventory.totals() if use_inventory else {}
        return self._nei(lambda: self.nei.craft_tree(item, int(count), have))

    def nei_machine_plan(self, side: str = "front", recipe: str = "", times: int | None = None,
                         lang: str | None = None) -> dict:
        if self._storage(side) is None:
            return err("BLOCKED", f"NO_INVENTORY: no inventory on {side}")

        def plan():
            result = self.nei.machine_plan(recipe)
            result["times"] = int(times) if times is not None else 1
            return result

        return self._nei(plan)
