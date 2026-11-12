"""Память агента на стенде: база на прогон, seed сценария, метрики, конфиги агентов."""

import json
import sqlite3

import yaml

from memory_mcp.config import Settings, _default_migrations_dir
from memory_mcp.repo import MemoryRepo
from memory_mcp.schemas import PoiRecord

from stand.config import load_config
from stand.runner import memory
from stand.runner.workspace import build_workspace
from stand.scenario import SCENARIOS_DIR, load_scenario
from test_workspace import CLAUDE, CODEX, OPENCODE

S01 = SCENARIOS_DIR / "s01-wall" / "scenario.yaml"
S09 = SCENARIOS_DIR / "s09-memory" / "scenario.yaml"


def _agent_writes(db, **poi):
    """То, что сделал бы агент: своя сессия и одно место."""
    repo = MemoryRepo(Settings(db_path=db, migrations_dir=_default_migrations_dir()))
    ctx = repo.open_context(memory.WORLD_ID, memory.PROFILE, "fake-robot")["session_id"]
    repo.remember_poi(ctx, PoiRecord(dim=0, **poi))
    repo.conn.close()


def test_empty_memory_by_default(tmp_path):
    db = tmp_path / "memory.db"
    before = memory.prepare_db(db, load_scenario(S01))
    assert before == {"pois": 0, "episodes": 0, "facts": 0, "agent_sessions": 0}
    m = memory.metrics(db, before, load_scenario(S01))
    assert m["used"] is False and m["pois_added"] == 0 and m["warehouse_remembered"] is False


def test_seed_and_metrics(tmp_path):
    s = load_scenario(S09)
    db = tmp_path / "memory.db"
    before = memory.prepare_db(db, s)
    # Seed: склад и урок, сессия стенда агентской не считается.
    assert before == {"pois": 1, "episodes": 1, "facts": 0, "agent_sessions": 0}
    _agent_writes(db, kind="other", label="cobblestone wall", x=100, y=64, z=100, radius=2)
    m = memory.metrics(db, before, s)
    assert m == {"used": True, "agent_sessions": 1, "pois_added": 1, "episodes_added": 0, "facts_added": 0,
                 "warehouse_remembered": True}


def test_memory_from_previous_run(tmp_path):
    s = load_scenario(S01)
    first = tmp_path / "run1" / "memory.db"
    memory.prepare_db(first, s)
    _agent_writes(first, kind="chest", label="warehouse", x=95, y=64, z=105, tags=["warehouse"])
    # Копия через backup видит записи, даже если они ещё в WAL.
    copy = tmp_path / "copy.db"
    memory.copy_db(first, copy)
    second = tmp_path / "run2" / "memory.db"
    before = memory.prepare_db(second, s, start_from=copy)
    assert before["pois"] == 1 and before["agent_sessions"] == 1
    assert memory.metrics(second, before, s)["warehouse_remembered"] is True


def test_workspace_has_memory_server_for_all_agents(tmp_path):
    s = load_scenario(S01)
    cfg = load_config()
    ws = build_workspace(tmp_path / "run", s, CLAUDE, cfg)
    server = json.loads(ws.mcp_config.read_text(encoding="utf-8"))["mcpServers"]["memory"]
    assert server["args"] == ["-m", "memory_mcp.server"] and server["env"]["MEMORY_DB"] == str(ws.memory_db)
    assert yaml.safe_load((ws.path / "oc-harness.yaml").read_text(encoding="utf-8"))["memory"] == {"profile": "player"}
    ws.cleanup()
    ws = build_workspace(tmp_path / "run", s, OPENCODE, cfg)
    mem = json.loads((ws.path / "opencode.json").read_text(encoding="utf-8"))["mcp"]["memory"]
    assert mem["environment"] == {"MEMORY_DB": str(ws.memory_db)}
    ws.cleanup()
    ws = build_workspace(tmp_path / "run", s, CODEX, cfg)
    assert any(a.startswith("mcp_servers.memory.env.MEMORY_DB=") for a in ws.mcp_args)
    ws.cleanup()


def test_hide_warehouse(tmp_path):
    ws = build_workspace(tmp_path / "run", load_scenario(S09), CLAUDE, load_config())
    assert "warehouse" not in yaml.safe_load((ws.path / "oc-harness.yaml").read_text(encoding="utf-8"))
    ws.cleanup()
