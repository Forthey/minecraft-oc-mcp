"""Профили возможностей fake-MCP.

Нужны, чтобы проверить агента при другом наборе возможностей робота: без зрения,
без RAG по документации или без данных NEI (нет игрока онлайн). disabled это
tools, которых у сервера нет. no_provider это tools, которые есть, но отвечают
NO_PROVIDER, как OC NEI Bridge без игрока и без кэша.
"""

from __future__ import annotations

NEI_TOOLS = {"nei_find", "nei_recipes", "nei_recipe", "nei_craft_tree", "nei_machine_plan", "craft_recipe"}

PROFILES: dict[str, dict[str, set[str]]] = {
    "full": {"disabled": set(), "no_provider": set()},
    "no-vision": {"disabled": {"surroundings", "geo_scan", "scan_area"}, "no_provider": set()},
    "no-docs": {"disabled": {"search_docs"}, "no_provider": set()},
    "no-nei": {"disabled": set(), "no_provider": NEI_TOOLS},
}
