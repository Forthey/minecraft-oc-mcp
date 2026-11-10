"""Сброс региона сценария и подготовка сцены.

Сброс возвращает каждую изменённую клетку к чистому плоскому миру и проверяет
результат повторным снимком. Если снимок не чистый, вызывающий делает полный сброс
(копия шаблона мира с перезапуском сервера).
"""

from __future__ import annotations

import shutil
from typing import Callable

from stand.config import Config
from stand.knowledge import Knowledge
from stand.scenario import WAREHOUSE_BLOCK, Scenario
from stand.server import process
from stand.world.backend import WorldBackend
from stand.world.blocks import Block, baseline_block, parse_block
from stand.world.snapshot import Snapshot

STACK = 64
CHEST_SLOTS = 27
EMPTY_ITEMS = "{Items:[]}"


def _is_container(b: Block, k: Knowledge) -> bool:
    item = k.item_for(b)
    return bool(item and k.container_slots(item))


def reset_region(
    world: WorldBackend,
    snapshot: Callable[[], Snapshot],
    scenario: Scenario,
    k: Knowledge,
) -> bool:
    """Возвращает регион к чистому миру. True, если повторный снимок чистый.

    Клетки обходятся сверху вниз, чтобы ничего не осыпалось. Контейнеры перед
    удалением очищаются пустым тегом Items, иначе содержимое высыпается на землю.
    """
    changed = snapshot().changed()
    for p in sorted(changed, key=lambda q: (-q[1], q[0], q[2])):
        b = changed[p]
        if _is_container(b, k):
            world.set_block_nbt(p, (b[0], 0), EMPTY_ITEMS)
        world.set_block(p, baseline_block(p[1]))
    return not snapshot().changed()


def warehouse_nbt(items: dict[str, int], item_ids: dict[str, int]) -> str:
    """NBT-тег сундука с предметами: стопки по 64 по слотам подряд."""
    entries = []
    slot = 0
    for item, count in items.items():
        name, meta = parse_block(item)
        if name not in item_ids:
            raise KeyError(f"no numeric id for item {item} in level.dat")
        left = count
        while left > 0:
            if slot >= CHEST_SLOTS:
                raise ValueError("warehouse items do not fit into one chest")
            n = min(STACK, left)
            entries.append(f"{{Slot:{slot}b,id:{item_ids[name]}s,Count:{n}b,Damage:{meta}s}}")
            slot += 1
            left -= n
    return "{Items:[" + ",".join(entries) + "]}"


def prepare_scene(world: WorldBackend, scenario: Scenario, k: Knowledge, item_ids: dict[str, int]) -> None:
    """Ставит блоки сцены снизу вверх и сундук склада с материалами.

    Склад наполняется и в мире, хотя fake-MCP держит его в памяти: так для real
    склад настоящий, а на демо видно содержимое.
    """
    for p in sorted(scenario.setup_blocks, key=lambda q: (q[1], q[0], q[2])):
        world.set_block(p, scenario.setup_blocks[p])
    wh = tuple(scenario.warehouse["pos"])
    world.set_block_nbt(wh, WAREHOUSE_BLOCK, warehouse_nbt(scenario.warehouse["items"], item_ids))


def full_reset(cfg: Config) -> None:
    """Останавливает сервер, заменяет мир копией шаблона и запускает сервер снова."""
    if process.is_running(cfg):
        process.stop_server(cfg)
    if cfg.world_dir.exists():
        shutil.rmtree(cfg.world_dir)
    shutil.copytree(cfg.world_template_dir, cfg.world_dir)
    proc = process.start_server(cfg)
    process.wait_rcon(cfg, proc=proc)


def ensure_server(cfg: Config) -> None:
    """Запускает сервер, если он не отвечает по RCON."""
    if not process.is_running(cfg):
        proc = process.start_server(cfg)
        process.wait_rcon(cfg, proc=proc)
