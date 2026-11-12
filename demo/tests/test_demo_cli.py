import socket
from dataclasses import replace

import pytest
import yaml

from demo import cli, lua_server
from stand.config import load_config


def test_installer_ships_only_the_client():
    text = lua_server.installer("http://h:1").decode()
    assert "/home/oc_mcp.lua" in text and "/home/oc_mcp/tools/move.lua" in text
    assert "tests/" not in text
    # Автозапуск дописывается в .shrc один раз.
    assert text.count('io.open(shrc, "a")') == 1 and 'text:find("oc_mcp", 1, true)' in text


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_lua_server_start_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "LUA_PID", tmp_path / "lua.pid")
    monkeypatch.setattr(cli, "LUA_LOG", tmp_path / "lua.log")
    port = _free_port()
    assert cli.start_lua(port) is True
    try:
        assert cli.lua_running(port)
        assert cli.start_lua(port) is False
    finally:
        assert cli.stop_lua() is True
    assert cli.stop_lua() is False


@pytest.fixture
def mods_cfg(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    manifest = tmp_path / "mods.yaml"
    manifest.write_text(yaml.safe_dump({"mods": [{"name": "a", "version": "1", "file": "a.jar"}]}), encoding="utf-8")
    return replace(load_config(), mods_cache=cache, mods_manifest=manifest)


def _args(dest, move_foreign=False):
    return type("A", (), {"dest": dest, "move_foreign": move_foreign})()


def test_client_mods_needs_cache(mods_cfg, tmp_path):
    assert cli.cmd_client_mods(mods_cfg, _args(tmp_path / "client" / "mods")) == 1


def test_client_mods_copies_and_moves_foreign(mods_cfg, tmp_path):
    (mods_cfg.mods_cache / "a.jar").write_bytes(b"jar")
    dest = tmp_path / "client" / "mods"
    dest.mkdir(parents=True)
    (dest / "fabric-1.21.jar").write_bytes(b"x")
    assert cli.cmd_client_mods(mods_cfg, _args(dest)) == 0
    assert (dest / "a.jar").read_bytes() == b"jar" and (dest / "fabric-1.21.jar").exists()
    assert cli.cmd_client_mods(mods_cfg, _args(dest, move_foreign=True)) == 0
    assert sorted(p.name for p in dest.iterdir()) == ["a.jar"]
    assert (dest.parent / "mods-disabled" / "fabric-1.21.jar").exists()
