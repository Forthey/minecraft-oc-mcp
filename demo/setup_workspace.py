"""Собирает demo/workspace: папку, из которой запускается Claude Code с haiku.

  uv run python demo/setup_workspace.py      (из корня репозитория)

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

from stand.config import load_config  # noqa: E402
from stand.server.setup import mod_versions  # noqa: E402

CLAUDE_MD = """\
# Робот OpenComputers

Для любой цели про робота в Minecraft используй скилл oc-orchestrator.
Инструменты робота даёт MCP-сервер `robot` (oc-mcp через адаптер контракта v2).

- Мир: Minecraft 1.7.10, выделенный сервер стенда, игрок подключён клиентом.
- Склад (сундук) и его сторона описаны в oc-harness.yaml.
- Стройплощадка: x 85..120, y 63..75, z 85..120. Пол плоский, верх земли y=63, строить с y=64.
- Координаты мировые, как в F3 у игрока.
"""


def main() -> int:
    cfg = load_config()
    scenario = yaml.safe_load(SCENARIO.read_text(encoding="utf-8"))
    versions = mod_versions(cfg.mods_manifest)

    WS.mkdir(parents=True, exist_ok=True)
    skills = WS / ".claude" / "skills"
    if skills.exists():
        shutil.rmtree(skills)
    shutil.copytree(ROOT / "agent" / "skills", skills)

    harness = {
        "versions": {"minecraft": "1.7.10", "ic2": versions.get("ic2", ""),
                     "opencomputers": versions.get("opencomputers", "")},
        "warehouse": {"pos": scenario["warehouse"]["pos"], "side": scenario["warehouse"]["side"]},
        "autonomy": "auto",
        "budgets": {"step_attempts": 3, "stage_redelegations": 2, "design_revisions": 1,
                    "research_sources": 6, "robot_calls_per_stage": 150},
        "safety": {"require_confirm": ["insert_fuel", "activate_machine", "dig_near_structure"]},
        "research": {"sources": ["rag", "web", "memory"], "cache_dir": ".oc-knowledge"},
    }
    (WS / "oc-harness.yaml").write_text(yaml.safe_dump(harness, sort_keys=False, allow_unicode=True), encoding="utf-8")

    robot = {
        "command": str(PYTHON),
        "args": ["-m", "adapter",
                 "--oc-mcp", str(ROOT / "bridge" / "server.py"),
                 "--world-id", "stand",
                 "--bridge-log", str(PLAY / "logs" / "bridge.log"),
                 "--map", "stand.adapter_map:oracle",
                 "--map-arg", f"scenario={SCENARIO}",
                 "--log", str(PLAY / "logs" / "action_log.jsonl")],
    }
    (PLAY / "logs").mkdir(exist_ok=True)
    (WS / ".mcp.json").write_text(json.dumps({"mcpServers": {"robot": robot}}, indent=2), encoding="utf-8")

    settings = {
        "model": "haiku",
        "permissions": {
            "allow": ["mcp__robot", "Read", "Glob", "Grep", "Edit", "Write", "WebSearch", "WebFetch"],
        },
    }
    (WS / ".claude" / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    # Одобрение серверов из .mcp.json Claude Code читает только из локальных настроек.
    local = {"enabledMcpjsonServers": ["robot"]}
    (WS / ".claude" / "settings.local.json").write_text(json.dumps(local, indent=2), encoding="utf-8")
    (WS / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")
    print(f"workspace ready: {WS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
