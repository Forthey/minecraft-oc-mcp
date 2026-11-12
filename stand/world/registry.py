"""Таблица числовых id блоков из level.dat (FML.ItemData).

В 1.7.10 Forge раздаёт числовые id при первом запуске мира и хранит соответствие
в level.dat: список пар K (имя с префиксом \\x01 для блоков, \\x02 для предметов)
и V (числовой id). Ванильные блоки там тоже есть.
"""

from __future__ import annotations

from pathlib import Path

from stand.world.nbt import read_nbt


def load_block_registry(level_dat: Path) -> dict[int, str]:
    """Возвращает отображение числовой id блока в имя вида mod:name."""
    root = read_nbt(level_dat.read_bytes())
    items = root.get("FML", {}).get("ItemData", [])
    out = {}
    for entry in items:
        key = entry.get("K", "")
        if key.startswith("\x01"):
            out[int(entry["V"])] = key[1:]
    if 0 not in out:
        out[0] = "minecraft:air"
    return out


def load_item_ids(level_dat: Path) -> dict[str, int]:
    """Числовые id предметов по имени (записи с префиксом \\x02). Нужны для NBT сундука."""
    root = read_nbt(level_dat.read_bytes())
    items = root.get("FML", {}).get("ItemData", [])
    return {e["K"][1:]: int(e["V"]) for e in items if e.get("K", "").startswith("\x02")}
