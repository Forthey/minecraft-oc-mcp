"""Разбор текстовых ответов oc-mcp в структуры для data конверта.

Форматы взяты из Lua oc-mcp: format.items для слотов, storage_scan для хранилищ,
move для неполного хода. oc-mcp печатает имя стека без damage, поэтому damage
считается 0, если его нет в тексте (TODO в docs/real-mcp-notes.md).
"""

from __future__ import annotations

import json
import re

SLOT_RE = re.compile(r"^slot (\d+): (\d+)x (\S+)(?: \((.*)\))?$")
MOVED_RE = re.compile(r"^moved (\d+) of \d+ blocks")
BLOCK_RE = re.compile(r"^Block: (\S+)$")
SIZE_RE = re.compile(r"^Storage has (\d+) slots\.$")


def nei_name(name: str) -> str:
    """Имя в форме mod:name:damage. Без damage в тексте дописывается 0."""
    parts = name.split(":")
    if len(parts) >= 3 and parts[-1].isdigit():
        return name
    return f"{name}:0"


def item_key(item: str) -> str:
    """mod:name без damage: так сравниваются предметы, пока oc-mcp не печатает damage."""
    parts = item.split(":")
    if len(parts) >= 3 and parts[-1].isdigit():
        return ":".join(parts[:-1])
    return item


def parse_slots(text: str) -> list[dict]:
    """Строки "slot N: Kx name (label)" в [{slot, count, name, label}]. Прочие строки пропускаются."""
    out = []
    for line in text.splitlines():
        m = SLOT_RE.match(line.strip())
        if m:
            out.append({"slot": int(m.group(1)), "count": int(m.group(2)), "name": nei_name(m.group(3)),
                        "label": m.group(4) or ""})
    return out


def parse_storage(text: str) -> dict:
    """Ответ storage_scan в {block, size, slots}. block None, если геолайзер не назвал блок."""
    block, size = None, None
    for line in text.splitlines():
        if m := BLOCK_RE.match(line.strip()):
            block = m.group(1)
        elif m := SIZE_RE.match(line.strip()):
            size = int(m.group(1))
    return {"block": block, "size": size, "slots": parse_slots(text)}


def parse_moved(text: str) -> int | None:
    """Сколько шагов сделал неполный move ("moved K of N blocks ..."), иначе None."""
    m = MOVED_RE.match(text)
    return int(m.group(1)) if m else None


def parse_json(text: str) -> dict | None:
    """JSON-объект из ответа (world_info, nei_*), None для другого текста."""
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None
