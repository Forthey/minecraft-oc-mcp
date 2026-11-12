"""Типы позиций и блоков, разбор строк блоков, базовое состояние плоского мира."""

from __future__ import annotations

Pos = tuple[int, int, int]
Block = tuple[str, int]

AIR: Block = ("minecraft:air", 0)

# Слои плоского мира стенда (generator-settings 2;7,59x1,3x3,2;1;).
FLOOR_Y = 63


def parse_block(s: str) -> Block:
    """Разбирает "mod:name" или "mod:name:meta". Без meta получается meta 0."""
    parts = s.split(":")
    if len(parts) >= 3 and parts[-1].lstrip("-").isdigit():
        return ":".join(parts[:-1]), int(parts[-1])
    return s, 0


def format_block(b: Block) -> str:
    """Обратное к parse_block: meta 0 не пишется."""
    name, meta = b
    return name if meta == 0 else f"{name}:{meta}"


def baseline_block(y: int) -> Block:
    """Блок чистого плоского мира на высоте y."""
    if y == 0:
        return ("minecraft:bedrock", 0)
    if 1 <= y <= 59:
        return ("minecraft:stone", 0)
    if 60 <= y <= 62:
        return ("minecraft:dirt", 0)
    if y == FLOOR_Y:
        return ("minecraft:grass", 0)
    return AIR
