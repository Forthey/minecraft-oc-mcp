"""Карта-оракул для адаптера: создаётся без сервера, сервер нужен только при обращении."""

import socket
from dataclasses import replace

import pytest

import stand.config
from stand.adapter_map import oracle
from stand.rcon import RconError
from stand.scenario import SCENARIOS_DIR


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_oracle_starts_without_server(monkeypatch):
    cfg = replace(stand.config.load_config(), rcon_port=_closed_port())
    monkeypatch.setattr(stand.config, "load_config", lambda: cfg)
    m = oracle(str(SCENARIOS_DIR / "s01-wall" / "scenario.yaml"))
    assert m.available and m.region_contains((100, 64, 100))
    with pytest.raises(RconError, match="uv run oc up"):
        m.occupied((100, 64, 100))
    # Следующее обращение снова пробует подключиться, а не падает на старом сокете.
    with pytest.raises(RconError, match="uv run oc up"):
        m.verify([{"pos": [100, 64, 100], "item": "minecraft:cobblestone"}])
