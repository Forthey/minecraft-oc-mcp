# minecraft-oc-mcp

MCP для управления роботом OpenComputers (Minecraft 1.7.10) LLM-агентом: Lua на роботе, MCP-мост,
адаптер контракта, память, скиллы агента и e2e-стенд для проверки.

Монорепо собрано из четырёх репозиториев команды с сохранением истории.
Что куда переехало: [MIGRATION.md](MIGRATION.md).
С чего начать: [docs/GUIDE.md](docs/GUIDE.md), от поднятия стенда до сценария агентом.
Что осталось доделать: [TODO.md](TODO.md).

```
агент (Claude Code, Codex, opencode) + agent/skills
  |
  +-- MCP stdio --> adapter/  контракт v2: конверт {ok, error_code, message, data}, move_to, place_at, verify_blocks
  |                   |
  |                   +-- MCP stdio (дочерний процесс) --> bridge/  MCP-сервер + HTTP :8765
  |                                                          ^
  |                                                          | poll
  |                                                        robot/  oc_mcp.lua на роботе
  |
  +-- MCP stdio --> memory/  память агента: POI, предпочтения, эпизоды (SQLite)
```

## Компоненты

| Каталог | Что это | Документация |
|---|---|---|
| `robot/` | Lua-скрипты робота: опрос моста, tools (move, place, craft, nei_*...) | [bridge/README.md](bridge/README.md) |
| `bridge/` | MCP-мост: stdio для агента, HTTP для робота. Только stdlib | [bridge/README.md](bridge/README.md) |
| `adapter/` | MCP-адаптер поверх моста: конверт контракта, коды ошибок, добавки | [docs/mcp-contract.md](docs/mcp-contract.md) |
| `memory/` | MCP-сервис памяти агента | [memory/README.md](memory/README.md) |
| `agent/` | Скиллы агента (`agent/skills/`), их валидатор и поведенческие сценарии | [agent/README.md](agent/README.md) |
| `stand/` | E2E-стенд: сервер Minecraft, fake-MCP, сценарии, судья, runner, conformance | [stand/README.md](stand/README.md) |
| `pathfinding/` | Pathfinder по сейву мира на Java и прототип на Python. Пока ни к чему не подключён | [pathfinding/java/README.md](pathfinding/java/README.md) |
| `demo/` | Интерактивное демо: агент (Claude Code, Codex или opencode) управляет настоящим роботом на сервере стенда. CLI `uv run oc` | [demo/README.md](demo/README.md) |
| `docs/` | Общие документы: сборка робота, контракт MCP, заметки о реальном MCP, сценарии стенда | [docs/robot-build.md](docs/robot-build.md) |

## Python

Один uv workspace на весь репозиторий: корневой проект (`adapter`, `stand`, `agent`) и `memory/`.

```bash
uv sync                 # .venv в корне, все пакеты editable, pytest
uv run pytest -q        # тесты adapter, stand, agent, memory (без живого сервера)
uv run pytest -m server # тесты, которым нужен запущенный сервер стенда
uv run python agent/tools/validate_skills.py
```

`bridge/` зависимостей не имеет и запускается по пути: `python bridge/server.py`.
