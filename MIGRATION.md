# Переезд в монорепо

До 2026-11-12 проект жил в четырёх репозиториях и папке `play/` вне git. Теперь всё здесь, история каждого
репозитория сохранена. Старые репозитории заморожены: новые коммиты только сюда.

| Было | Репозиторий |
|---|---|
| `oc-mcp` | github.com/Tozarin/oc-mcp |
| `minecraft-oc-mcp-client` | github.com/Forthey/minecraft-oc-mcp-client |
| `minecraft-oc-memory-mcp` | github.com/sbrandprog/minecraft-oc-memory-mcp |
| `Minecraft-Path-Finding-Algo` | github.com/PajiloyLis/Minecraft-Path-Finding-Algo |
| `play/` | не было в git |

## Что куда переехало

### oc-mcp

| Было | Стало |
|---|---|
| `lua/oc_mcp.lua`, `lua/oc_mcp/` | `robot/oc_mcp.lua`, `robot/oc_mcp/` |
| `.tasks/craft_recipe_test/` | `robot/tests/craft_recipe_test/` (как есть, без интеграции в тесты) |
| `bridge/` | `bridge/` |
| `README.md` | `bridge/README.md` (установка моста и робота) |
| `.gitignore` | удалён, правила в корневом `.gitignore` |

### minecraft-oc-mcp-client

| Было | Стало |
|---|---|
| `skills/` | `agent/skills/` |
| `tools/validate_skills.py` | `agent/tools/validate_skills.py` |
| `tests/test_repo.py`, `tests/test_validate_skills.py`, `tests/conftest.py` | `agent/tests/` |
| `tests/scenarios/` | `agent/tests/scenarios/` |
| `README.md` | `agent/README.md` |
| `adapter/` | `adapter/` |
| `tests/adapter/` | `adapter/tests/` |
| `tests/adapter/conftest.py` | `adapter/tests/adapter_harness.py` (см. ниже) |
| `stand/` | `stand/` |
| `tests/stand/` | `stand/tests/` |
| `docs/` | `docs/` |
| `pytest.ini`, `requirements-dev.txt`, `stand/requirements.txt` | удалены, всё в корневом `pyproject.toml` |
| `.gitignore` | корневой `.gitignore` |

### minecraft-oc-memory-mcp

| Было | Стало |
|---|---|
| весь репозиторий | `memory/` (структура внутри та же) |
| `uv.lock` | корневой `uv.lock` |
| `.python-version` | корневой `.python-version` |
| `.gitignore` | корневой `.gitignore` (`memory/local/`, `memory/data/`, `*.db`) |

### Minecraft-Path-Finding-Algo

| Было | Стало |
|---|---|
| `java-pathfinding/` | `pathfinding/java/` |
| `python_test_macro_planner/` | `pathfinding/prototype-py/` |
| `.gitignore` | корневой `.gitignore` (`pathfinding/java/target/`) |

### play/

| Было | Стало |
|---|---|
| `play/*.py`, `play/*.ps1`, `scenario.yaml`, `README.md` | `demo/`; скрипты `.ps1` заменены CLI `uv run oc` (`demo/cli.py`) |
| `play/workspace/` | не в git, генерируется: `uv run oc workspace` (или `uv run oc up`) |
| `play/logs/` | не в git, `demo/logs/` |

## Что изменилось, кроме путей

- **Один uv workspace.** `uv sync` в корне создаёт один `.venv` для всего: корневой проект ставит пакеты
  `adapter`, `stand`, `agent` в editable-режиме, `memory/` входит в workspace как пакет `memory-mcp`.
  `PYTHONPATH` больше не нужен, `python -m adapter` и `python -m stand...` работают из любого каталога.
  `uv sync` запускайте из корня: внутри `memory/` он синхронизирует только зависимости memory.
- **Тесты.** `uv run pytest -q` в корне гоняет все четыре набора: `adapter/tests`, `stand/tests`, `agent/tests`,
  `memory/tests`. Маркер `server` и `-m "not server"` по умолчанию остались прежними.
- **`adapter/tests/conftest.py` → `adapter_harness.py`.** В нём были только хелперы, их импортировали через
  `from conftest import ...`. В монорепо три `conftest.py`, и импорт подхватывал чужой. Теперь
  `from adapter_harness import bridge, make_sim`.
- **Импорт валидатора скиллов:** `from tools.validate_skills import ...` → `from agent.tools.validate_skills import ...`.
- **`oc_mcp_dir` в `stand/config.yaml`.** Ключ означает каталог, в котором лежит `bridge/`. Раньше `../oc-mcp`,
  теперь `.` (корень монорепо), это значение по умолчанию. Если в вашем `stand/config.local.yaml`
  есть `oc_mcp_dir: ../oc-mcp`, удалите строку.
- **Скрипты демо** ищут всё от корня монорепо и берут python из корневого `.venv`.
- **`.mailmap`** объединяет два написания одного автора (Startsev Matvey / Старцев Матвей).

## История

Каждый репозиторий переписан `git filter-repo --to-subdirectory-filter <каталог>` и влит отдельным merge-коммитом
(`Merge <owner>/<repo> into <каталог>/`). Авторы, даты и сообщения сохранены, хэши коммитов новые.
Структура по ролям сделана после слияния обычными коммитами с `git mv`, поэтому `git log --follow` и `git blame`
проходят через переносы:

```bash
git log --follow -- adapter/robot.py     # история с времён client/adapter/robot.py
git log -- 'pathfinding/'                 # всё по pathfinding
```

## Если у вас был старый клон

1. Склонируйте этот репозиторий заново и выполните `uv sync` в корне.
2. Перенесите локальные файлы, которых нет в git (из старого `minecraft-oc-mcp-client/`):
   - `stand/config.local.yaml` (без `oc_mcp_dir`, см. выше);
   - `stand/server/instance/`, `stand/server/world-template/`, `stand/server/mods-cache/*.jar`:
     можно скопировать или пересоздать через `uv run python -m stand.server setup --pin`;
   - `stand/runs/` при желании.
3. Если в старом `minecraft-oc-memory-mcp/` были `data/` (база памяти) или `local/`, перенесите их в `memory/data/` и `memory/local/`.
4. Демо: `uv run oc up`, затем `claude` в `demo/workspace`.
5. В конфигах MCP-клиентов поменяйте пути: `oc-mcp/bridge/server.py` → `bridge/server.py`,
   python из `minecraft-oc-mcp-client/.venv` → корневой `.venv`.

## Известные проблемы, перенесённые как есть

- Спеки `docs/superpowers/specs/*.md`, на которые ссылаются README и docs, ни в одном репозитории не были закоммичены.
- `adapter` подключает карту мира из `stand` (`--map stand.adapter_map:oracle`), то есть продовый путь зависит от стенда.
- A\* реализован трижды: `adapter/pathfinding.py`, `stand/fake_mcp/pathfinding.py`, `pathfinding/java/`.
  Java-версия ни к чему не подключена.
