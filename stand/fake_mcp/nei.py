"""Эмуляция OC NEI Bridge по фикстурам знаний стенда.

Ответы повторяют форму `result` из nei.tools мода (docs/AGENT_INTEGRATION.md
OC NEI Bridge): id предметов в форме mod:name:damage, рецепты с id, категорией
и входами за один запуск. Реальный мод берёт рецепты из NEI клиента игрока,
здесь они берутся из stand/knowledge/recipes.json.
"""

from __future__ import annotations

import hashlib
import json

from stand.knowledge import CRAFTING, Knowledge, normalize_id
from stand.world.blocks import parse_block

# Слоты робота для клеток 1-9 сетки крафта: инвентарь робота шириной 4 слота.
CRAFT_GRID: tuple[int, ...] = (1, 2, 3, 5, 6, 7, 9, 10, 11)

SHAPED = ("Shaped Crafting", "codechicken.nei.recipe.ShapedRecipeHandler")
SHAPELESS = ("Shapeless Crafting", "codechicken.nei.recipe.ShapelessRecipeHandler")
SMELTING = ("Smelting", "codechicken.nei.recipe.FurnaceRecipeHandler")
FIND_LIMIT = 50


class NeiError(Exception):
    """Ошибка nei.tools: код OC NEI Bridge (UNKNOWN_ITEM, UNKNOWN_RECIPE) и текст."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def nei_id(item: str) -> str:
    """Id предмета в форме NEI: mod:name:damage, damage 0 дописывается."""
    name, meta = parse_block(item)
    return f"{name}:{meta}"


def recipe_id(recipe: dict) -> str:
    """Устойчивый id рецепта: хэш его содержимого, как у мода."""
    digest = hashlib.sha1(json.dumps(recipe, sort_keys=True).encode("utf-8")).hexdigest()
    return "r" + digest[:16]


class FakeNei:
    """Ответы nei.tools (find, recipes, recipe, craft, plan) по фикстурам Knowledge."""

    def __init__(self, k: Knowledge):
        self.k = k
        self._by_id = {recipe_id(r): r for r in k.recipes}

    # Предметы

    def label(self, item: str) -> str:
        """Название предмета из фикстур, иначе его id."""
        it = self.k.items.get(normalize_id(item))
        return it["name"] if it else nei_id(item)

    def _known(self, item: str) -> str:
        """Короткий id известного предмета. Неизвестный даёт UNKNOWN_ITEM."""
        short = normalize_id(item)
        if short in self.k.items:
            return short
        for r in self.k.recipes:
            if r["output"]["item"] == short or short in r["ingredients"]:
                return short
        raise NeiError("UNKNOWN_ITEM", f"unknown item: {item}")

    def find(self, text: str, limit: int | None = None) -> dict:
        """Поиск по названию и id, лучшие первыми."""
        found = self.k.search_items(text, limit or FIND_LIMIT)
        items = [{"item": nei_id(f["item"]), "label": f["name"], "mod": f["mod"]} for f in found]
        return {"items": items, "total": len(items)}

    # Рецепты

    def _category(self, r: dict) -> tuple[str, str, str | None]:
        """Название категории, её id и overlay рецепта."""
        if r["type"] == "crafting_shaped":
            return SHAPED[0], SHAPED[1], "crafting"
        if r["type"] == "crafting_shapeless":
            return SHAPELESS[0], SHAPELESS[1], "crafting"
        machine = r.get("machine", "")
        if normalize_id(machine) == "minecraft:furnace":
            return SMELTING[0], SMELTING[1], "smelting"
        label = self.label(machine)
        return label, "ic2." + label.replace(" ", ""), None

    def _short(self, r: dict) -> dict:
        cat, cat_id, overlay = self._category(r)
        out = {
            "id": recipe_id(r),
            "cat": cat,
            "catId": cat_id,
            "in": [{"item": nei_id(i), "n": n} for i, n in r["ingredients"].items()],
            "out": [{"item": nei_id(r["output"]["item"]), "n": r["output"]["count"]}],
        }
        if overlay:
            out["overlay"] = overlay
        return out

    def _grid(self, r: dict) -> list[dict]:
        """Клетки сетки верстака с слотами робота. Shapeless идёт по клеткам подряд."""
        cells: list[tuple[int, str]] = []
        if r["type"] == "crafting_shaped":
            for row, line in enumerate(r["grid"]):
                for col, value in enumerate(line):
                    if value:
                        cells.append((row * 3 + col + 1, normalize_id(value)))
        else:
            for item, n in r["ingredients"].items():
                for _ in range(n):
                    cells.append((len(cells) + 1, item))
        return [{"cell": c, "robotSlot": CRAFT_GRID[c - 1], "item": nei_id(i), "count": 1} for c, i in cells]

    def _get(self, rid: str) -> dict:
        r = self._by_id.get(rid)
        if r is None:
            # Подсказка из nei.lua oc-mcp: агент часто передаёт id предмета вместо id рецепта.
            hint = (f" '{rid}' is an item id, not a recipe id: get recipe ids (like r7fbebd0471463308) "
                    "from nei_recipes.") if ":" in rid else ""
            raise NeiError("UNKNOWN_RECIPE", f"unknown recipe: {rid}{hint}")
        return r

    def recipes(self, item: str, usages: bool = False, category: str | None = None,
                limit: int | None = None) -> dict:
        """Рецепты, которые дают предмет, или с usages те, где он ингредиент."""
        short = self._known(item)
        if usages:
            found = [r for r in self.k.recipes if short in r["ingredients"]]
        else:
            found = self.k.get_recipes(short)
        out = [self._short(r) for r in found]
        if category:
            needle = category.lower()
            out = [s for s in out if needle in s["cat"].lower() or needle in s["catId"].lower()]
        total = len(out)
        if limit:
            out = out[:limit]
        return {"results": [{"item": nei_id(short), "total": total, "recipes": out}]}

    def recipe(self, rid: str) -> dict:
        """Рецепт полностью: позиции ингредиентов и для верстака сетка со слотами робота."""
        r = self._get(rid)
        full = self._short(r)
        if r["type"] in CRAFTING:
            grid = self._grid(r)
            full["grid"] = grid
            positions = [(g["cell"], g["item"]) for g in grid]
        else:
            positions = [(i + 1, nei_id(item)) for i, item in enumerate(r["ingredients"])]
        full["ingredients"] = [
            {"slot": cell, "items": [self._stack(item)]} for cell, item in positions
        ]
        return full

    def _stack(self, item: str) -> dict:
        name, meta = parse_block(item)
        return {"name": name, "damage": meta, "size": 1, "label": self.label(item)}

    # Дерево крафта

    def _crafting_recipe(self, item: str) -> dict | None:
        return next((r for r in self.k.get_recipes(item) if r["type"] in CRAFTING), None)

    def craft_tree(self, item: str, count: int, have: dict[str, int]) -> dict:
        """Шаги крафта в порядке исполнения, сырьё и нужные категории.

        Дерево берётся из Knowledge.plan_materials, have вычитается. Шаг узла идёт
        после шагов его детей, одинаковые предметы сливаются суммой запусков.
        """
        short = self._known(item)
        plan = self.k.plan_materials(short, count, have)
        steps: dict[str, dict] = {}
        raw: dict[str, int] = {}

        def visit(node: dict) -> None:
            for child in node["children"]:
                visit(child)
            if node.get("missing"):
                raw[node["item"]] = raw.get(node["item"], 0) + node["missing"]
            if not node.get("crafts"):
                return
            step = steps.get(node["item"])
            if step is None:
                r = self._crafting_recipe(node["item"])
                step = dict(self._short(r), runs=0, makes=nei_id(node["item"]))
                step["recipe"] = step.pop("id")
                step["grid"] = self._grid(r)
                steps[node["item"]] = step
            step["runs"] += node["crafts"]

        visit(plan["tree"])
        machines: dict[str, dict] = {}
        for s in steps.values():
            m = machines.setdefault(s["catId"], {"catId": s["catId"], "cat": s["cat"], "steps": 0, "runs": 0})
            m["steps"] += 1
            m["runs"] += s["runs"]
        return {
            "item": nei_id(short),
            "count": count,
            "steps": list(steps.values()),
            "raw": [{"item": nei_id(i), "n": n} for i, n in raw.items()],
            "machinesNeeded": list(machines.values()),
        }

    def machine_plan(self, rid: str) -> dict:
        """Слоты машины: входы по слотам с 1 подряд, выход в следующем слоте.

        Упрощение: реальный мод берёт слоты из GUI машины.
        """
        r = self._get(rid)
        put = [{"item": nei_id(i), "n": n, "slot": s + 1} for s, (i, n) in enumerate(r["ingredients"].items())]
        return {"recipe": rid, "put": put, "take": [{"slot": len(put) + 1}]}
