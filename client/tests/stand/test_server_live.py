"""Проверки на живом сервере. Запуск: python -m stand.server start && pytest -m server."""

import pytest

from stand.config import load_config
from stand.rcon import Rcon

pytestmark = pytest.mark.server

# Блоки, которые сценарии ставят через /setblock: имя, meta. Meta None значит
# любую: сундук при установке сам поворачивается и меняет meta (0 становится 3).
BLOCKS = [
    ("IC2:blockGenerator", 0),   # Generator
    ("IC2:blockMachine", 3),     # Macerator
    ("IC2:blockGenerator", 5),   # Nuclear Reactor
    ("IC2:blockReactorChamber", 0),
    ("minecraft:chest", None),
]


@pytest.fixture(scope="module")
def rcon():
    cfg = load_config()
    with Rcon(cfg.rcon_host, cfg.rcon_port, cfg.rcon_password, timeout=10) as r:
        yield r


@pytest.mark.parametrize("i,block", list(enumerate(BLOCKS)))
def test_setblock_and_testforblock(rcon, i, block):
    name, meta = block
    x, y, z = 100 + 2 * i, 64, 110
    placed = rcon.command(f"setblock {x} {y} {z} {name} {meta or 0} replace")
    assert "placed" in placed.lower(), placed
    found = rcon.command(f"testforblock {x} {y} {z} {name} {-1 if meta is None else meta}")
    assert "successfully" in found.lower(), found


def test_tile_entity_exists(rcon):
    """У машины IC2 после /setblock есть tile entity.

    В 1.7.10 нет /blockdata. testforblock с NBT-тегом сравнивает тег только у
    блоков с tile entity, а у остальных тег пропускает. Поэтому заведомо неверная
    координата x проваливает проверку ровно тогда, когда tile entity есть.
    """
    rcon.command("setblock 120 64 110 IC2:blockMachine 3 replace")
    out = rcon.command("testforblock 120 64 110 IC2:blockMachine 3 {x:999}")
    assert "did not have the required nbt keys" in out.lower(), out
    rcon.command("setblock 122 64 110 minecraft:planks 0 replace")
    control = rcon.command("testforblock 122 64 110 minecraft:planks 0 {x:999}")
    assert "successfully" in control.lower(), control
