"""Инвентарь робота и контейнеры: слоты со стопками."""

from __future__ import annotations


class Inventory:
    """Слоты по stack предметов. Добавление сначала дополняет начатые стопки."""

    def __init__(self, slots: int = 16, stack: int = 64):
        self.size = slots
        self.stack = stack
        self.slots: list[list | None] = [None] * slots

    def count(self, item: str) -> int:
        return sum(s[1] for s in self.slots if s and s[0] == item)

    def space_for(self, item: str) -> int:
        """Сколько штук item ещё поместится."""
        free = 0
        for s in self.slots:
            if s is None:
                free += self.stack
            elif s[0] == item:
                free += self.stack - s[1]
        return free

    def add(self, item: str, count: int) -> int:
        """Кладёт предметы и возвращает, сколько не поместилось."""
        left = count
        for s in self.slots:
            if left and s and s[0] == item and s[1] < self.stack:
                n = min(left, self.stack - s[1])
                s[1] += n
                left -= n
        for i, s in enumerate(self.slots):
            if left and s is None:
                n = min(left, self.stack)
                self.slots[i] = [item, n]
                left -= n
        return left

    def remove(self, item: str, count: int) -> bool:
        """Забирает ровно count штук. Если не хватает, ничего не меняет и возвращает False."""
        if self.count(item) < count:
            return False
        left = count
        for i in range(len(self.slots) - 1, -1, -1):
            s = self.slots[i]
            if left and s and s[0] == item:
                n = min(left, s[1])
                s[1] -= n
                left -= n
                if s[1] == 0:
                    self.slots[i] = None
        return True

    def totals(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.slots:
            if s:
                out[s[0]] = out.get(s[0], 0) + s[1]
        return out

    def slots_view(self) -> list[dict]:
        return [
            {"slot": i, "item": s[0] if s else None, "count": s[1] if s else 0}
            for i, s in enumerate(self.slots)
        ]

    def summary(self) -> dict:
        totals = sorted(self.totals().items(), key=lambda t: (-t[1], t[0]))
        return {
            "used": sum(1 for s in self.slots if s),
            "total": self.size,
            "top": [{"item": i, "count": c} for i, c in totals[:5]],
        }
