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


def test_hub_start_stop(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(cli, "HUB_PID", tmp_path / "hub.pid")
    monkeypatch.setattr(cli, "HUB_LOG", tmp_path / "hub.log")
    port = _free_port()
    cmd = [sys.executable, "-m", "adapter", "serve", "--port", str(port), "--bridge-log", str(tmp_path / "b.log")]
    assert cli.start_hub(port, cmd) is True
    try:
        assert cli.hub_running(port)
        assert cli.start_hub(port, cmd) is False
    finally:
        assert cli.stop_hub() is True
    assert cli.stop_hub() is False


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


def test_workspace_for_all_agents(tmp_path, monkeypatch):
    import json

    from demo import agent_workspace as aw

    monkeypatch.setattr(aw, "WS", tmp_path / "ws")
    monkeypatch.setattr(aw, "LOGS", tmp_path / "logs")
    ws = aw.build()
    for rel in aw.SKILL_DIRS.values():
        assert (ws / rel / "oc-orchestrator" / "SKILL.md").exists()
    assert "robot" in json.loads((ws / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    opencode = json.loads((ws / "opencode.json").read_text(encoding="utf-8"))["mcp"]["robot"]
    assert opencode == {"type": "remote", "url": aw.MCP_URL, "enabled": True}
    assert json.loads((ws / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["robot"] == \
        {"type": "http", "url": aw.MCP_URL}
    assert aw.hub_args()[:3] == ["-m", "adapter", "serve"]
    assert "skills/oc-orchestrator/SKILL.md" in (ws / "AGENTS.md").read_text(encoding="utf-8")
    # Память: тот же сервер во всех форматах, база demo/memory.db.
    claude = json.loads((ws / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["memory"]
    assert claude["args"] == ["-m", "memory_mcp.server"] and claude["env"]["MEMORY_DB"] == str(aw.MEMORY_DB)
    mem = json.loads((ws / "opencode.json").read_text(encoding="utf-8"))["mcp"]["memory"]
    assert mem["environment"] == {"MEMORY_DB": str(aw.MEMORY_DB)}
    assert json.loads((ws / ".claude" / "settings.local.json").read_text(encoding="utf-8")) ==         {"enabledMcpjsonServers": ["robot", "memory"]}
    assert "mcp__memory" in json.loads((ws / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["allow"]
    harness = (ws / "oc-harness.yaml").read_text(encoding="utf-8")
    assert "profile: player" in harness and "model" in harness
    assert "oc-orchestrator" in (ws / "CLAUDE.md").read_text(encoding="utf-8")


def test_agent_command(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/bin/{name}")
    codex = cli.agent_command("codex", ["--model", "m"])
    assert codex[0] == "/bin/codex" and codex[-2:] == ["--model", "m"]
    assert any(a.startswith("mcp_servers.robot.url=") for a in codex)
    assert "mcp_servers.robot.tool_timeout_sec=600" in codex
    assert any(a.startswith("mcp_servers.memory.env.MEMORY_DB=") for a in codex)
    assert cli.agent_command("claude", []) == ["/bin/claude"]
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    with pytest.raises(FileNotFoundError):
        cli.agent_command("opencode", [])


def test_memory_show_and_reset(tmp_path, monkeypatch, capsys):
    from memory_mcp.config import Settings, _default_migrations_dir
    from memory_mcp.repo import MemoryRepo
    from memory_mcp.schemas import EpisodeRecord, PoiRecord

    from demo import agent_workspace as aw

    db = tmp_path / "memory.db"
    monkeypatch.setattr(aw, "MEMORY_DB", db)
    assert cli.main(["memory"]) == 0 and "memory is empty" in capsys.readouterr().out
    repo = MemoryRepo(Settings(db_path=db, migrations_dir=_default_migrations_dir()))
    ctx = repo.open_context("stand", "player", "robot-1")["session_id"]
    repo.remember_poi(ctx, PoiRecord(kind="machine", label="macerator", dim=0, x=101, y=64, z=100,
                                     item_uid="IC2:blockMachine:3"))
    repo.remember_episode(ctx, EpisodeRecord(goal="wall", outcome="success", lesson="bottom row first"))
    repo.conn.close()
    assert cli.main(["memory"]) == 0
    out = capsys.readouterr().out
    assert "machine 'macerator' IC2:blockMachine:3 at (101, 64, 100)" in out and "bottom row first" in out
    assert cli.main(["memory", "--reset"]) == 0 and not db.exists()
