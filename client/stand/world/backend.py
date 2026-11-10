"""Бэкенды мира для fake-MCP: настоящий сервер через RCON и мир в памяти для тестов."""

from __future__ import annotations

from typing import Protocol

from stand.rcon import Rcon
from stand.world.blocks import Block, Pos, baseline_block


class WorldError(RuntimeError):
    """Сервер отверг команду изменения мира."""


class WorldBackend(Protocol):
    """Что fake-MCP умеет делать с миром."""

    def set_block(self, p: Pos, b: Block) -> None:
        """Ставит блок, воздух означает сломать."""

    def test_block(self, p: Pos, b: Block, any_meta: bool = False) -> bool:
        """Стоит ли в позиции блок b (при any_meta сравнивается только имя)."""


class RconWorld:
    """Мир настоящего сервера: /setblock и /testforblock."""

    def __init__(self, rcon: Rcon):
        self.rcon = rcon

    def set_block(self, p: Pos, b: Block) -> None:
        x, y, z = p
        resp = self.rcon.command(f"setblock {x} {y} {z} {b[0]} {b[1]} replace")
        low = resp.lower()
        # "couldn't be placed" сервер отвечает, когда блок уже такой же.
        if "placed" not in low:
            raise WorldError(f"setblock {p} {b}: {resp}")

    def test_block(self, p: Pos, b: Block, any_meta: bool = False) -> bool:
        x, y, z = p
        meta = -1 if any_meta else b[1]
        resp = self.rcon.command(f"testforblock {x} {y} {z} {b[0]} {meta}")
        return "successfully" in resp.lower()


class MemoryWorld:
    """Мир в памяти: плоский мир плюс записанные блоки. Для тестов и conformance."""

    def __init__(self, blocks: dict[Pos, Block] | None = None):
        self.blocks: dict[Pos, Block] = dict(blocks or {})

    def get(self, p: Pos) -> Block:
        return self.blocks.get(p, baseline_block(p[1]))

    def set_block(self, p: Pos, b: Block) -> None:
        if b == baseline_block(p[1]):
            self.blocks.pop(p, None)
        else:
            self.blocks[p] = b

    def test_block(self, p: Pos, b: Block, any_meta: bool = False) -> bool:
        actual = self.get(p)
        return actual[0] == b[0] and (any_meta or actual[1] == b[1])
