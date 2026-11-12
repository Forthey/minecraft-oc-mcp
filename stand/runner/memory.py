"""Память агента (memory/) на стенде: база на прогон, начальное содержимое, метрики.

Каждый прогон получает свою базу в рабочей папке агента, по умолчанию пустую: иначе прогоны
перестают быть повторяемыми. Сценарий может положить в неё факты заранее (ключ memory.seed),
а флаг --memory-from начинает с базы прошлого прогона. После прогона база копируется в
папку прогона, а в results.json пишется, что агент с ней делал.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from memory_mcp.config import Settings, _default_migrations_dir
from memory_mcp.repo import MemoryRepo
from memory_mcp.schemas import EpisodeRecord, PoiRecord, PreferenceRecord

from stand.scenario import Scenario

MCP_NAME = "memory"
# world_id совпадает с тем, что отдаёт world_info fake-MCP и адаптер стенда (--world-id stand).
WORLD_ID = "stand"
PROFILE = "player"
# Под этим robot_id стенд пишет начальное содержимое, чтобы отличать его сессию от сессий агента.
SEED_ROBOT = "stand-seed"


def server_spec(db: Path) -> dict:
    """stdio MCP-сервер памяти с базой db."""
    return {"command": sys.executable, "args": ["-m", "memory_mcp.server"], "env": {"MEMORY_DB": str(db)}}


def copy_db(src: Path, dst: Path) -> None:
    """Копия базы SQLite с учётом WAL: простое копирование файла может потерять последние записи."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    target = sqlite3.connect(dst)
    try:
        source.backup(target)
        # Копия одним файлом, без -wal и -shm рядом: её читают и переносят в другие прогоны.
        target.execute("PRAGMA journal_mode=DELETE")
    finally:
        source.close()
        target.close()


def _repo(db: Path) -> MemoryRepo:
    return MemoryRepo(Settings(db_path=db, migrations_dir=_default_migrations_dir()))


def counts(db: Path) -> dict:
    """Сколько в базе мест, уроков, фактов и сессий агента."""
    if not db.exists():
        return {"pois": 0, "episodes": 0, "facts": 0, "agent_sessions": 0}
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        one = lambda q, *a: con.execute(q, a).fetchone()[0]  # noqa: E731
        return {
            "pois": one("SELECT count(*) FROM poi"),
            "episodes": one("SELECT count(*) FROM episode"),
            "facts": one("SELECT count(*) FROM core"),
            "agent_sessions": one("SELECT count(*) FROM context WHERE robot_id <> ?", SEED_ROBOT),
        }
    finally:
        con.close()


def prepare_db(db: Path, s: Scenario, start_from: Path | None = None) -> dict:
    """Готовит базу прогона: копия start_from (или пустая) плюс memory.seed сценария.

    Возвращает счётчики до прогона, от них считаются изменения.
    """
    if start_from is not None:
        if not start_from.exists():
            raise FileNotFoundError(f"memory database {start_from} does not exist")
        copy_db(start_from, db)
    repo = _repo(db)
    try:
        seed = s.memory.get("seed") or {}
        if seed:
            ctx = repo.open_context(WORLD_ID, PROFILE, SEED_ROBOT)["session_id"]
            for p in seed.get("pois", []):
                x, y, z = p["pos"]
                repo.remember_poi(ctx, PoiRecord(
                    kind=p["kind"], label=p["label"], dim=0, x=x, y=y, z=z, radius=p.get("radius", 0),
                    item_uid=p.get("item_uid", ""), tags=p.get("tags", []), source=p.get("source", "observed")))
            for e in seed.get("episodes", []):
                repo.remember_episode(ctx, EpisodeRecord(**e))
            for f in seed.get("preferences", []):
                repo.set_preference(ctx, PreferenceRecord(**f))
    finally:
        repo.conn.close()
    return counts(db)


def _warehouse_remembered(db: Path, s: Scenario) -> bool:
    x, y, z = s.warehouse["pos"]
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT count(*) FROM poi WHERE kind = 'chest' AND abs(x - ?) <= 1 AND abs(y - ?) <= 1 "
                          "AND abs(z - ?) <= 1", (x, y, z)).fetchone()
    finally:
        con.close()
    return row[0] > 0


def metrics(db: Path, before: dict, s: Scenario) -> dict:
    """Что агент сделал с памятью за прогон."""
    if not db.exists():
        return {"used": False, "agent_sessions": 0, "pois_added": 0, "episodes_added": 0, "facts_added": 0,
                "warehouse_remembered": False}
    after = counts(db)
    return {
        "used": after["agent_sessions"] > before["agent_sessions"],
        "agent_sessions": after["agent_sessions"] - before["agent_sessions"],
        "pois_added": after["pois"] - before["pois"],
        "episodes_added": after["episodes"] - before["episodes"],
        "facts_added": after["facts"] - before["facts"],
        "warehouse_remembered": _warehouse_remembered(db, s),
    }
