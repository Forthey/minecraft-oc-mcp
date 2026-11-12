"""Карта мира для добавок: какие клетки заняты и что где стоит.

Робот видит только соседние блоки, поэтому карту даёт плагин. Стенд даёт оракул по
снимку мира (stand/adapter_map.py). Без плагина карты нет, и добавки, которым она
нужна, отвечают UNSUPPORTED.
"""

from __future__ import annotations

from typing import Protocol

Pos = tuple[int, int, int]


class WorldMap(Protocol):
    """Интерфейс карты. Позиции мировые."""

    available: bool

    def region_contains(self, p: Pos) -> bool:
        """Входит ли клетка в область, по которой можно ездить и строить."""

    def occupied(self, p: Pos) -> bool:
        """Занята ли клетка блоком (блок робота считается свободным)."""

    def invalidate(self) -> None:
        """Сбрасывает кэш: мир изменился (поставлен или сломан блок)."""

    def verify(self, expected: list[dict]) -> tuple[list[dict], list[dict]]:
        """Сверка [{pos, item}] с миром: (missing, wrong), элементы {pos, item}."""


class NoMap:
    """Карты нет: добавки с картой отвечают UNSUPPORTED."""

    available = False

    def region_contains(self, p: Pos) -> bool:
        return False

    def occupied(self, p: Pos) -> bool:
        return False

    def invalidate(self) -> None:
        pass

    def verify(self, expected: list[dict]) -> tuple[list[dict], list[dict]]:
        return [], []
