"""Собирает demo/workspace: папку, из которой агент управляет роботом.

  uv run oc workspace        (его же вызывают uv run oc up и uv run oc agent)

Папка годится сразу для трёх агентов:
  Claude Code  .claude/skills, .mcp.json, .claude/settings.json, CLAUDE.md
  opencode     .opencode/skills, opencode.json, AGENTS.md
  Codex        skills/ и AGENTS.md; MCP-сервер передаётся флагами -c (uv run oc agent codex)

Повторный запуск безопасен: скиллы копируются заново (подтянуть правки из репозитория),
журналы агента (.oc-tasks, .oc-knowledge) не трогаются.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import yaml

PLAY = Path(__file__).resolve().parent
ROOT = PLAY.parent
WS = PLAY / "workspace"
SCENARIO = PLAY / "scenario.yaml"
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

LOGS = PLAY / "logs"
# База памяти агента: переживает перезапуски агента, сервера и пересборку workspace. В .gitignore.
MEMORY_DB = PLAY / "memory.db"
# Профиль игрока для memory: чьи предпочтения и договорённости. Мир и робот берутся из world_info.
PROFILE = "player"

from stand.config import load_config  # noqa: E402
from stand.server.setup import mod_versions  # noqa: E402

MCP_NAME = "robot"
MEMORY_NAME = "memory"
AGENTS = ("claude", "codex", "opencode")
# Куда каждый агент смотрит за скиллами. Codex читает их по ссылке из AGENTS.md.
SKILL_DIRS = {"claude": ".claude/skills", "opencode": ".opencode/skills", "codex": "skills"}

CONTEXT = """Инструменты робота даёт MCP-сервер `robot` (oc-mcp через адаптер контракта v2).
Память между задачами (склад, машины, уроки) даёт MCP-сервер `memory`, как его вести, сказано в oc-orchestrator.

- Мир: Minecraft 1.7.10, выделенный сервер стенда, игрок подключён клиентом.
- Склад (сундук) и его сторона описаны в oc-harness.yaml.
- Стройплощадка: x 85..120, y 63..75, z 85..120. Пол плоский, верх земли y=63, строить с y=64.
- Координаты мировые, как в F3 у игрока.
"""

CLAUDE_MD = f"""# Робот OpenComputers

Для любой цели про робота в Minecraft используй скилл oc-orchestrator.

{CONTEXT}"""

AGENTS_MD = f"""# Робот OpenComputers

Для любой цели про робота в Minecraft следуй skills/oc-orchestrator/SKILL.md. Остальные скиллы лежат
рядом в skills/, ссылки вида ../references/... в них отсчитываются от папки скилла.

{CONTEXT}"""


def robot_server() -> dict:
    """stdio MCP-сервер робота: адаптер поверх моста oc-mcp и карта-оракул стенда."""
    return {
        "command": str(PYTHON),
        "args": ["-m", "adapter",
                 "--oc-mcp", str(ROOT / "bridge" / "server.py"),
                 "--world-id", "stand",
                 "--bridge-log", str(LOGS / "bridge.log"),
                 "--map", "stand.adapter_map:oracle",
                 "--map-arg", f"scenario={SCENARIO}",
                 "--log", str(LOGS / "action_log.jsonl")],
    }


def memory_server() -> dict:
    """stdio MCP-сервер памяти агента (memory/) с базой demo/memory.db."""
    return {"command": str(PYTHON), "args": ["-m", "memory_mcp.server"], "env": {"MEMORY_DB": str(MEMORY_DB)}}


def servers() -> dict[str, dict]:
    """Все MCP-серверы демо по имени: робот и память."""
    return {MCP_NAME: robot_server(), MEMORY_NAME: memory_server()}


def _opencode(spec: dict) -> dict:
    out = {"type": "local", "command": [spec["command"], *spec["args"]], "enabled": True}
    if spec.get("env"):
        out["environment"] = spec["env"]
    return out


def _copy_skills(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(ROOT / "agent" / "skills", dest)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def build() -> Path:
    """Собирает или обновляет demo/workspace. Возвращает путь к нему."""
    cfg = load_config()
    scenario = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    versions = mod_versions(cfg.mods_manifest)

    WS.mkdir(parents=True, exist_ok=True)
    for rel in SKILL_DIRS.values():
        _copy_skills(WS / rel)

    harness = {
        "versions": {"minecraft": "1.7.10", "ic2": versions.get("ic2", ""),
                     "opencomputers": versions.get("opencomputers", "")},
        "warehouse": {"pos": scenario["warehouse"]["pos"], "side": scenario["warehouse"]["side"]},
        "autonomy": "auto",
        "budgets": {"step_attempts": 3, "stage_redelegations": 2, "design_revisions": 1,
                    "research_sources": 6, "robot_calls_per_stage": 150},
        "safety": {"require_confirm": ["insert_fuel", "activate_machine", "dig_near_structure"]},
        "research": {"sources": ["rag", "web", "model"], "cache_dir": ".oc-knowledge"},
        "memory": {"profile": PROFILE},
    }
    (WS / "oc-harness.yaml").write_text(yaml.safe_dump(harness, sort_keys=False, allow_unicode=True), encoding="utf-8")

    LOGS.mkdir(exist_ok=True)
    mcp = servers()

    # Claude Code. Одобрение серверов из .mcp.json он читает только из локальных настроек.
    _write_json(WS / ".mcp.json", {"mcpServers": mcp})
    _write_json(WS / ".claude" / "settings.json", {
        "model": "haiku",
        "permissions": {
            "allow": [*(f"mcp__{name}" for name in mcp), "Read", "Glob", "Grep", "Edit", "Write",
                      "WebSearch", "WebFetch"],
        },
    })
    _write_json(WS / ".claude" / "settings.local.json", {"enabledMcpjsonServers": list(mcp)})
    (WS / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")

    # opencode и Codex читают AGENTS.md. Codex получает MCP-сервер флагами при запуске (oc agent codex).
    _write_json(WS / "opencode.json", {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {name: _opencode(spec) for name, spec in mcp.items()},
    })
    (WS / "AGENTS.md").write_text(AGENTS_MD, encoding="utf-8")
    return WS


def main() -> int:
    print(f"workspace ready: {build()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
