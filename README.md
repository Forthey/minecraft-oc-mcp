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
  +-- MCP HTTP :8765/mcp --> python -m adapter serve   один долгоживущий процесс, любое число клиентов
  |                           adapter/  контракт v2: конверт {ok, error_code, message, data}, move_to, place_at
  |                           bridge/   очередь команд в том же процессе
  |                           :8765 /poll /result для робота, /get.lua установщик Lua
  |                                 ^
  |                                 | poll
  |                               robot/  oc_mcp.lua на роботе
  |
  |   другие режимы: python -m adapter --in-process (stdio, мост в процессе),
  |   python -m adapter --oc-mcp bridge/server.py (stdio, мост дочерним процессом),
  |   python bridge/server.py (голый мост по stdio без контракта v2)
  |   карта для move_to/place_at: --explore-db PATH (разведка робота) или --map (оракул стенда);
  |   --memory-db (или MEMORY_DB): hazard и waypoint из memory; --pf-jar/--pf-world: Java pathfinding
  |
  +-- MCP stdio --> memory/  память агента: POI, предпочтения, эпизоды (SQLite)
```

## Компоненты

| Каталог | Что это | Документация |
|---|---|---|
| `robot/` | Lua-скрипты робота: опрос моста, tools (move, place, craft, nei_*...) | [bridge/README.md](bridge/README.md) |
| `bridge/` | MCP-мост: stdio для агента, HTTP для робота. Только stdlib | [bridge/README.md](bridge/README.md) |
| `adapter/` | MCP-адаптер поверх моста: конверт контракта, коды ошибок, добавки; хаб `python -m adapter serve` | [docs/mcp-contract.md](docs/mcp-contract.md) |
| `memory/` | MCP-сервис памяти агента | [memory/README.md](memory/README.md) |
| `agent/` | Скиллы агента (`agent/skills/`), их валидатор и поведенческие сценарии | [agent/README.md](agent/README.md) |
| `stand/` | E2E-стенд: сервер Minecraft, fake-MCP, сценарии, судья, runner, conformance | [stand/README.md](stand/README.md) |
| `pathfinding/` | Pathfinder по сейву мира на Java и прототип на Python. Java-версию адаптер зовёт для дальних `move_to` (`--pf-jar`) | [pathfinding/java/README.md](pathfinding/java/README.md) |
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

## Запуск в своей игре

1. `uv sync`. По желанию собрать jar pathfinding ([pathfinding/java/README.md](pathfinding/java/README.md)).
2. В `opencomputers.cfg` добавить `"allow ip:127.0.0.1"` перед `"deny private"`. Робот: Internet Card, Geolyzer, Inventory Controller, Navigation Upgrade. Вне области карты апгрейда поставить рядом Waypoint с подписью-координатами (`0 64 0`).
3. Хаб: `scripts/hub.sh`. Окружение: `OC_WORLD_ID`, `MEMORY_DB`, по желанию `OC_SAVE_DIR` и `OC_PF_JAVA` (удобно держать в `.env`).
4. На роботе: `wget -f http://127.0.0.1:8765/get.lua /home/get.lua`, `/home/get.lua`, `oc_mcp`.
5. В MCP-клиенте: `robot` по URL `http://127.0.0.1:8765/mcp` и `memory` (`.venv/bin/python -m memory_mcp.server` с тем же `MEMORY_DB`).
6. Скопировать `agent/skills/` в каталог скиллов агента и запускать агента из корня репозитория (там `oc-harness.yaml`). Точка входа: `oc-orchestrator`.
