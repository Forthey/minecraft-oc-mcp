"""Знания fake-MCP: предметы, рецепты и документация из фикстур.

Заменяет RAG и дамп NEI команды (пункты 1 и 3), пока их нет. Фикстуры лежат в
stand/knowledge/, сценарий может добавить свои через раздел knowledge.

ID предметов имеют вид mod:name или mod:name:meta, meta 0 не пишется.
Блок предмета задаётся полем block. Поле meta_mask говорит, какие биты meta блока
значимы при сравнении: 0 у сундука (он сам поворачивается), 3 у бревна (старшие
биты хранят ось). По умолчанию 15, то есть meta сравнивается целиком.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from stand.world.blocks import Block, format_block, parse_block

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
CRAFTING = {"crafting_shaped", "crafting_shapeless"}
MAX_DEPTH = 8
SNIPPET = 200
WORD_RE = re.compile(r"\w+")


def normalize_id(item: str) -> str:
    """Приводит ID к каноническому виду: mod:name:0 становится mod:name."""
    return format_block(parse_block(item))


def _ingredients(recipe: dict) -> dict[str, int]:
    if "ingredients" in recipe:
        return {normalize_id(k): int(v) for k, v in recipe["ingredients"].items()}
    counts = Counter(normalize_id(c) for row in recipe.get("grid", []) for c in row if c)
    return dict(counts)


def _words(text: str) -> set[str]:
    return set(WORD_RE.findall(text.lower()))


class Knowledge:
    """Индекс предметов, рецептов и документов."""

    def __init__(self, items: list[dict], recipes: list[dict], docs: list[dict], base_dir: Path | None = None):
        self.base_dir = base_dir
        self.items: dict[str, dict] = {}
        for it in items:
            it = dict(it, id=normalize_id(it["id"]))
            self.items[it["id"]] = it
        self.recipes = []
        for r in recipes:
            r = dict(r)
            r["output"] = {"item": normalize_id(r["output"]["item"]), "count": int(r["output"].get("count", 1))}
            r["ingredients"] = _ingredients(r)
            self.recipes.append(r)
        self.docs = list(docs)
        self._by_block: dict[str, list[tuple[Block, str, int]]] = {}
        for it in self.items.values():
            if it.get("block"):
                block = parse_block(it["block"])
                self._by_block.setdefault(block[0], []).append((block, it["id"], int(it.get("meta_mask", 15))))

    @classmethod
    def load(cls, base_dir: Path, extra: dict | None = None) -> "Knowledge":
        """Читает фикстуры из base_dir и добавляет раздел knowledge сценария."""
        def read(name):
            path = base_dir / name
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

        extra = extra or {}
        items = {normalize_id(i["id"]): i for i in read("items.json")}
        for i in extra.get("items", []):
            items[normalize_id(i["id"])] = i
        recipes = read("recipes.json") + list(extra.get("recipes", []))
        docs = read("docs.json") + list(extra.get("docs", []))
        return cls(list(items.values()), recipes, docs, base_dir=base_dir)

    # Предметы

    def get_item(self, item_id: str) -> dict | None:
        """Карточка предмета: item, name, mod, description. None, если предмет неизвестен."""
        it = self.items.get(normalize_id(item_id))
        if it is None:
            return None
        return {"item": it["id"], "name": it["name"], "mod": it["mod"], "description": it.get("description", "")}

    def search_items(self, query: str, limit: int = 10) -> list[dict]:
        """Предметы, у которых в ID или названии есть слова запроса, лучшие первыми."""
        q = _words(query)
        scored = []
        for it in self.items.values():
            words = _words(it["name"]) | _words(it["id"].replace(":", " "))
            score = len(q & words)
            if score:
                scored.append((-score, it["id"], it))
        scored.sort(key=lambda t: (t[0], t[1]))
        return [{"item": it["id"], "name": it["name"], "mod": it["mod"]} for _, _, it in scored[:limit]]

    def block_for(self, item_id: str) -> Block | None:
        """Блок, который ставится из предмета, или None, если предмет не ставится."""
        it = self.items.get(normalize_id(item_id))
        return parse_block(it["block"]) if it and it.get("block") else None

    def item_for(self, block: Block) -> str | None:
        """Предмет, из которого получается блок, с учётом meta_mask."""
        for (name, meta), item_id, mask in self._by_block.get(block[0], []):
            if meta & mask == block[1] & mask:
                return item_id
        return None

    def _mask(self, block_name: str) -> int:
        entries = self._by_block.get(block_name)
        return entries[0][2] if entries else 15

    def block_matches(self, expected: Block, actual: Block) -> bool:
        """Совпадают ли блоки с учётом незначимых битов meta."""
        if expected[0] != actual[0]:
            return False
        mask = self._mask(expected[0])
        return expected[1] & mask == actual[1] & mask

    def container_slots(self, item_id: str) -> int:
        """Число слотов, если блок предмета это контейнер, иначе 0."""
        it = self.items.get(normalize_id(item_id))
        return int(it.get("container_slots", 0)) if it else 0

    # Рецепты

    def get_recipes(self, item_id: str) -> list[dict]:
        """Все рецепты, которые дают предмет."""
        item_id = normalize_id(item_id)
        return [r for r in self.recipes if r["output"]["item"] == item_id]

    def _crafting_recipe(self, item_id: str) -> dict | None:
        for r in self.get_recipes(item_id):
            if r["type"] in CRAFTING:
                return r
        return None

    def plan_materials(self, item_id: str, count: int, have: dict[str, int]) -> dict:
        """Дерево крафта одного предмета и то, чего не хватает. have не меняется."""
        return self.plan_many({normalize_id(item_id): count}, have)

    def plan_many(self, needs: dict[str, int], have: dict[str, int]) -> dict:
        """Как plan_materials, но для нескольких предметов из общего запаса.

        Возвращает {"tree": дерево первого предмета, "trees": все деревья,
        "missing": [{"item", "count", "craftable"}]}. craftable означает, что у
        недостающего предмета есть рецепт крафта, но раскрыть его не удалось
        (цикл или глубина). Предметы только с машинными рецептами craftable=False.
        """
        stock = {normalize_id(k): v for k, v in have.items()}
        missing: dict[str, dict] = {}
        trees = []
        for item_id, count in needs.items():
            trees.append(self._expand(normalize_id(item_id), count, stock, frozenset(), 0, missing))
        return {"tree": trees[0] if trees else None, "trees": trees, "missing": list(missing.values())}

    def _expand(self, item_id, count, stock, path, depth, missing) -> dict:
        node = {"item": item_id, "count": count, "children": []}
        take = min(stock.get(item_id, 0), count)
        if take:
            stock[item_id] -= take
            node["from_stock"] = take
        need = count - take
        if need == 0:
            return node
        recipe = self._crafting_recipe(item_id)
        if recipe is None or item_id in path or depth >= MAX_DEPTH:
            entry = missing.setdefault(item_id, {"item": item_id, "count": 0, "craftable": recipe is not None})
            entry["count"] += need
            node["missing"] = need
            return node
        out = recipe["output"]["count"]
        crafts = math.ceil(need / out)
        node["crafts"] = crafts
        for ing, per in recipe["ingredients"].items():
            node["children"].append(self._expand(ing, per * crafts, stock, path | {item_id}, depth + 1, missing))
        leftover = crafts * out - need
        if leftover:
            stock[item_id] = stock.get(item_id, 0) + leftover
        return node

    # Документация

    def search_docs(self, query: str, mod: str | None = None, limit: int = 5) -> list[dict]:
        """Документы по совпадению слов запроса. Совпадение в заголовке весит вдвое больше."""
        q = _words(query)
        scored = []
        for d in self.docs:
            if mod and d.get("mod", "").lower() != mod.lower():
                continue
            score = 2 * len(q & _words(d["title"])) + len(q & _words(d["text"]))
            if score:
                scored.append((-score, d["doc_id"], d))
        scored.sort(key=lambda t: (t[0], t[1]))
        return [
            {"doc_id": d["doc_id"], "title": d["title"], "snippet": d["text"][:SNIPPET],
             "version": d.get("version", ""), "mod": d.get("mod", "")}
            for _, _, d in scored[:limit]
        ]
