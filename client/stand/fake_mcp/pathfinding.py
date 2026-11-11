"""Поиск пути для fake-MCP. Код живёт в adapter.pathfinding, им пользуются и адаптер, и стенд."""

from adapter.pathfinding import NEIGHBOURS, astar

__all__ = ["NEIGHBOURS", "astar"]
