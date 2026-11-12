"""Перевод текста ошибки oc-mcp в код контракта.

oc-mcp отдаёт ошибки свободным текстом из Lua (lua/oc_mcp/tools/*.lua) или из моста.
Шаблоны ниже повторяют эти строки и проверяются в порядке таблицы, первое совпадение
решает. Порядок важен: например, "no recipe matches the grid, or there is no free slot"
должен дать NO_RECIPE раньше, чем "no free slot" даст INVENTORY_FULL.

Если oc-mcp переформулирует сообщение, шаблон перестанет совпадать и код станет
UNKNOWN. Тексты для тестов лежат в stand/fake_mcp/texts.py, их надо обновлять вместе.
"""

from __future__ import annotations

import re

RULES: list[tuple[str, re.Pattern]] = [
    ("CONNECTION_LOST", re.compile(r"OpenComputers did not respond within")),
    ("UNSUPPORTED", re.compile(r"^tool \S+ is disabled")),
    ("NO_PROVIDER", re.compile(r"^NO_PROVIDER:")),
    ("UNKNOWN_ITEM", re.compile(r"^UNKNOWN_ITEM:")),
    ("NO_RECIPE", re.compile(r"^UNKNOWN_RECIPE:|no recipe matches|not a crafting-table recipe")),
    ("BLOCKED", re.compile(r"^bad argument: ")),
    ("BLOCKED", re.compile(r"^moved \d+ of \d+ blocks")),
    ("BLOCKED", re.compile(r"is occupied by")),
    ("NO_ITEM", re.compile(r"slot (\d+ )?is empty|crafting grid is empty|not enough ingredients|cannot equip from slot")),
    ("INVENTORY_FULL", re.compile(r"no free slot|no room outside the crafting grid|inventory (is )?full|slot \d+ is full")),
    ("TOOL_BROKEN", re.compile(r"cannot break .* with the equipped tool")),
    ("CANT_PLACE", re.compile(r"^cannot place from slot")),
    ("BLOCKED", re.compile(r"nothing to hit|no storage on side|holds a different item|cannot take items|cannot put items")),
]


def classify(text: str) -> str:
    """Код контракта для текста ошибки oc-mcp. Нераспознанный текст даёт UNKNOWN."""
    for code, pattern in RULES:
        if pattern.search(text):
            return code
    return "UNKNOWN"
