"""Карта мира стенда для адаптера (python -m adapter --map stand.adapter_map:oracle).

Оракул: карта по снимку региона сценария, честная только на стенде. В обычной игре
такой карты нет, там её заменит разведка или поиск пути из пункта 2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from stand.knowledge import KNOWLEDGE_DIR, Knowledge, normalize_id
from stand.world.backend import WorldBackend
from stand.world.blocks import AIR, ROBOT_BLOCKS, Pos, baseline_block, parse_block
from stand.world.snapshot import Box, Snapshot


def memory_snapshot(world, region: Box) -> Snapshot:
    """Снимок региона из мира в памяти (MemoryWorld). Для тестов."""
    blocks = {}
    for p in region.iter():
        b = world.get(p)
        if b != baseline_block(p[1]):
            blocks[p] = b
    return Snapshot(region, blocks)


class SnapshotMap:
    """WorldMap адаптера по снимку региона. Снимок кэшируется до invalidate."""

    available = True

    def __init__(self, region: Box, k: Knowledge, snapshot: Callable[[], Snapshot], world: WorldBackend):
        self.region = region
        self.k = k
        self._snapshot = snapshot
        self.world = world
        self._cache: Snapshot | None = None

    def region_contains(self, p: Pos) -> bool:
        return self.region.contains(tuple(p))

    def occupied(self, p: Pos) -> bool:
        if self._cache is None:
            self._cache = self._snapshot()
        b = self._cache.get(tuple(p))
        return b != AIR and b[0] not in ROBOT_BLOCKS

    def invalidate(self) -> None:
        self._cache = None

    def verify(self, expected: list[dict]) -> tuple[list[dict], list[dict]]:
        """Сверка как у fake-MCP: testforblock через backend мира."""
        missing, wrong = [], []
        for e in expected:
            p = tuple(e["pos"])
            short = normalize_id(e["item"])
            block = AIR if short == AIR[0] else (self.k.block_for(short) or parse_block(short))
            any_meta = self.k.meta_mask(block[0]) != 15
            if self.world.test_block(p, block, any_meta=any_meta):
                continue
            entry = {"pos": list(p), "item": short}
            (missing if self.world.test_block(p, AIR) else wrong).append(entry)
        return missing, wrong


class _StandRcon:
    """RCON карты-оракула с подсказкой, что делать, если сервер стенда не запущен."""

    def __init__(self, rcon):
        self.rcon = rcon

    def command(self, cmd: str) -> str:
        from stand.rcon import RconError

        try:
            return self.rcon.command(cmd)
        except RconError as e:
            raise RconError(f"stand server is not reachable over RCON ({e}): start it with `uv run oc up`, "
                            "move_to, place_at and verify_blocks need it") from e


def oracle(scenario: str) -> SnapshotMap:
    """Карта по региону сценария на сервере стенда: снимок region-файлов и testforblock через RCON.

    RCON подключается при первом обращении карты, а не при запуске адаптера: агент стартует и без
    сервера, tools без карты работают сразу, а move_to, place_at и verify_blocks отвечают ошибкой,
    пока сервер не поднят.
    """
    from stand.config import load_config
    from stand.rcon import ReconnectingRcon
    from stand.scenario import load_scenario
    from stand.world.backend import RconWorld
    from stand.world.snapshot import capture

    cfg = load_config()
    s = load_scenario(Path(scenario))
    rcon = _StandRcon(ReconnectingRcon(cfg.rcon_host, cfg.rcon_port, cfg.rcon_password, timeout=10))
    return SnapshotMap(s.region, Knowledge.load(KNOWLEDGE_DIR, s.knowledge),
                       lambda: capture(rcon, cfg.world_dir, s.region), RconWorld(rcon))
