"""Добавки контракта v2: высокоуровневые tools в мировых координатах.

В oc-mcp их нет, их даёт наш адаптер. Здесь они собраны из примитивов модели
робота (place, состояние, инвентарь) и поиска пути по оракул-карте региона, так
же, как их будет собирать адаптер. Класс подмешивается в RobotSim и пользуется его
полями: pos, facing, occ, region, inventory, k, nei, world.
"""

from __future__ import annotations

from stand.fake_mcp.envelope import err, ok
from stand.fake_mcp.geometry import DIRS, FACINGS, add, sub
from stand.fake_mcp.nei import nei_id
from adapter.pathfinding import NEIGHBOURS
from stand.knowledge import normalize_id
from stand.world.blocks import AIR, parse_block

VERIFY_PAGE = 50


class Additions:
    """move_to, face, place_at, get_status, verify_blocks, search_docs."""

    def _outside(self, target) -> dict:
        return err("OUT_OF_RANGE", f"{list(target)} is outside the allowed area")

    def move_to(self, x: int, y: int, z: int, policy: str = "avoid") -> dict:
        target = (int(x), int(y), int(z))
        if not self.region.contains(target):
            return self._outside(target)
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
            return err("NO_ENERGY", "not enough energy", {"pos": list(self.pos)})
        for p in to_dig:
            self._break(p)
        self.pos = target
        return ok(f"Moved to {list(target)} in {steps} steps.",
                  {"pos": list(target), "steps": steps, "dug": [list(p) for p in to_dig]})

    def face(self, direction: str) -> dict:
        if direction not in FACINGS:
            return err("BLOCKED", f"unknown direction {direction}, use north, south, east or west")
        self.facing = direction
        return ok(f"Facing {direction}.", {"facing": direction})

    def _side_towards(self, target) -> str:
        """Поворачивает робота к соседней клетке и возвращает сторону для place."""
        d = sub(target, self.pos)
        for name in FACINGS:
            if DIRS[name] == d:
                self.facing = name
                return "front"
        return "up" if d[1] > 0 else "down"

    def place_at(self, x: int, y: int, z: int, item: str, from_: str | None = None) -> dict:
        target = (int(x), int(y), int(z))
        short = normalize_id(item)
        if self.k.get_item(short) is None:
            return err("UNKNOWN_ITEM", f"unknown item {item}")
        if not self.region.contains(target):
            return self._outside(target)
        if self.k.block_for(short) is None:
            return err("CANT_PLACE", f"{nei_id(short)} is not a placeable block")
        slot = self.inventory.first_slot_with(short)
        if slot is None:
            return err("NO_ITEM", f"no {nei_id(short)} in the robot inventory")
        if target in self.occ:
            return err("CANT_PLACE", f"{list(target)} is occupied by {self._item_of(self.occ[target])}")
        if from_ is not None:
            if from_ not in DIRS:
                return err("BLOCKED", f"unknown approach side {from_}")
            approaches = [add(target, DIRS[from_])]
        else:
            approaches = [add(target, d) for d in NEIGHBOURS]
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
        if not self._spend(steps=steps):
            return err("NO_ENERGY", "not enough energy", {"pos": list(self.pos)})
        self.pos = best[-1]
        placed = self.place(self._side_towards(target), slot)
        if not placed["ok"]:
            return placed
        return ok(f"Placed {nei_id(short)} at {list(target)} from slot {slot}.",
                  {"pos": list(target), "slot": slot})

    def get_status(self) -> dict:
        inventory = [{"slot": i, "count": c[1], "name": nei_id(c[0])}
                     for i in range(1, self.inventory.size + 1) if (c := self.inventory.slot(i))]
        message = f"At {list(self.pos)} facing {self.facing}, {len(inventory)} inventory slots used."
        return ok(message, {"pos": list(self.pos), "facing": self.facing, "inventory": inventory})

    def verify_blocks(self, expected: list[dict], page: int = 0) -> dict:
        start = int(page) * VERIFY_PAGE
        chunk = expected[start:start + VERIFY_PAGE]
        missing, wrong = [], []
        for e in chunk:
            p = tuple(e["pos"])
            short = normalize_id(e["item"])
            block = AIR if short == AIR[0] else (self.k.block_for(short) or parse_block(short))
            any_meta = self.k.meta_mask(block[0]) != 15
            if self.world.test_block(p, block, any_meta=any_meta):
                continue
            entry = {"pos": list(p), "item": nei_id(short)}
            (missing if self.world.test_block(p, AIR) else wrong).append(entry)
        nxt = int(page) + 1 if start + VERIFY_PAGE < len(expected) else None
        message = f"Checked {len(chunk)}: {len(missing)} missing, {len(wrong)} wrong."
        return ok(message, {"checked": len(chunk), "missing": missing, "wrong": wrong, "next_page": nxt})

    def search_docs(self, query: str, mod: str | None = None, limit: int = 5) -> dict:
        docs = self.k.search_docs(query, mod, int(limit))
        return ok(f"{len(docs)} documents.", {"docs": docs})
