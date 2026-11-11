# E2E-стенд

Стенд проверяет агента со скиллами из `skills/` от начала до конца: агент получает цель, через MCP управляет роботом, в мире Minecraft появляется постройка, судья сверяет её с ожиданием и считает метрики.

Дизайн: [docs/superpowers/specs/2026-11-10-e2e-stand-design.md](../docs/superpowers/specs/2026-11-10-e2e-stand-design.md). Сценарии и что из них показывать на демо: [docs/stand-scenarios.md](../docs/stand-scenarios.md).

## Как устроено

```
runner   сбрасывает регион, ставит сцену, создаёт рабочую папку агента, запускает агента
агент    поднимает MCP-сервер робота и вызывает tools
fake-MCP меняет мир через RCON (/setblock), инвентарь и склад держит в памяти, пишет action log
судья    после прогона читает мир из region-файлов сервера и сравнивает с ожиданием
runner   считает метрики и пишет results.json, report.md, summary.md
```

Сервер Forge 1.7.10 работает headless, клиент игры нужен только чтобы посмотреть на постройку глазами (подключиться к `localhost:25565`, офлайн-режим).

Судья не зависит ни от MCP, ни от отчёта агента: он читает мир напрямую. Поэтому стенд одинаково оценивает и fake-MCP, и реальный сервер команды.

## Установка

Нужны Python 3.10 или новее и Java 8. Forge 1.7.10 на более новой Java не запускается.

- **Linux:** `sudo apt install openjdk-8-jre-headless`, путь `/usr/lib/jvm/java-8-openjdk-amd64/bin/java` уже стоит в `stand/config.yaml`.
- **Windows:** установщик Temurin 8 (JRE, x64) с adoptium.net. Путь к `java.exe` записать в `stand/config.local.yaml`:

  ```yaml
  java_path: C:\Program Files\Eclipse Adoptium\jre-8.0.xxx-hotspot\bin\java.exe
  ```

`stand/config.local.yaml` перекрывает любые ключи `stand/config.yaml` и не попадает в git. Туда же кладутся пароль RCON и настройки реального MCP.

Зависимости и сервер:

```bash
uv venv .venv && uv pip install -p .venv -r requirements-dev.txt
.venv/bin/python -m stand.server setup --pin
```

`setup` проверяет Java, ставит Forge, скачивает моды по `stand/server/mods.yaml` (IC2, OpenComputers, NEI с зависимостями), пишет конфиги и создаёт шаблон мира. Повторный запуск безопасен. Если мод не скачивается, положите jar в `stand/server/mods-cache/` руками.

На Windows вместо `.venv/bin/python` используйте `.venv\Scripts\python`.

## Команды

```bash
python -m stand.server start | stop | status           сервер
python -m stand.runner run --scenario s01-wall --agent claude [--repeat 3] [--profile no-docs]
python -m stand.runner suite --agents claude,codex [--scenarios s01-wall,s07-relative] [--repeat 3]
python -m stand.runner prepare --scenario s03-obstacle  сбросить регион и поставить сцену (для ручной проверки)
python -m stand.runner judge --scenario s03-obstacle    оценить текущий мир без агента
python -m stand.runner report                           пересобрать stand/runs/summary.md
python -m stand.conformance --mcp fake | real           контрактные проверки MCP-сервера
```

`run` и `suite` сами запускают сервер, если он не отвечает.

**Агенты** описаны в `stand/agents.yaml`: `claude`, `claude-haiku`, `codex`, `opencode` и `script`. Модель задаётся флагом в команде, поэтому для другой модели добавьте запись с другим именем. Агент `script` не использует LLM: он выполняет `stand/scenarios/<id>/script.json` и нужен, чтобы бесплатно проверить, что стенд работает целиком.

Прогон агентом-скриптом и e2e-тесты на сервере:

```bash
python -m stand.runner run --scenario s01-wall --agent script
pytest -m server
```

## Что лежит в папке прогона

`stand/runs/<дата>-<сценарий>-<агент>-<n>/`:

| Файл | Что в нём |
|---|---|
| `results.json` | все метрики прогона |
| `report.md` | отчёт для человека: вердикт, диф судьи, нарушения со ссылками на строки action log |
| `action_log.jsonl` | каждый вызов tool: аргументы, `ok`, код ошибки, внедрённый сбой |
| `transcript.jsonl` | вывод агента (stream-json у Claude, события JSON у codex и opencode) |
| `journal/` | копия `.oc-tasks` агента: journal.md, decisions.md, tried.md, spec.json |
| `snapshot.json`, `judge.json` | снимок региона и вердикт судьи |
| `private/mcp_scenario.yaml` | копия сценария без ожидания, которую получил fake-MCP |

`stand/runs/summary.md` собирает таблицу сценарий на агент: доля PASS по повторам, медианы времени, вызовов и стоимости, ложные успехи, нарушения.

## Метрики

**Статус прогона:**

- `PASS`: судья принял постройку
- `FAIL`: не принял
- `ASKED`: агент закончил вопросом пользователю, не заявив успех
- `TIMEOUT`: вышло время сценария, дерево процессов агента убито
- `CRASH`: агент упал с ненулевым кодом, и судья не принял постройку
- `SKIPPED`: сценарий требует fake-MCP, а стенд работает с реальным.

**Ложный успех:** агент записал в журнал `phase=final status=DONE`, а судья дал FAIL. Это самый важный сигнал, что проверки в скиллах не работают.

**Нарушения правил скиллов:**

| Правило | Когда срабатывает |
|---|---|
| `repeated_call` | тот же tool с теми же аргументами и той же ошибкой вызван в третий раз (правило 1 из `error-handling.md`) |
| `done_without_verify` | этап в журнале отмечен DONE, а строки проверки этого этапа после него нет |
| `dig_near_structure` | робот сломал блок рядом со своей постройкой |
| `budget_exceeded` | в журнале бюджет превышен (`used > limit`) или вызовов на этап больше `robot_calls_per_stage` |
| `answer_leak` | агент обращался к `stand/scenarios`, `stand/knowledge` или к копии сценария для fake-MCP |

Токены и стоимость берутся из вывода агента. Claude отдаёт всё, codex только токены, opencode ничего.

## Упрощения fake-MCP

Fake-MCP нужен до готовности реального сервера и отличается от него в следующем:

- робот перемещается мгновенно, может висеть в воздухе и в мире не виден
- блоки ставятся без опоры, гравитации нет
- склад, инвентарь и слоты машин живут в памяти (сундук склада в мире наполняется только для наглядности)
- `use` ничего не делает, `read_block_info` всегда возвращает `BLOCKED`: функциональных проверок пока нет
- `get_known_map` возвращает то же, что полный `scan_area`: fake-MCP знает весь регион
- знания (`search_items`, `get_recipes`, `plan_materials`, `search_docs`) берутся из фикстур `stand/knowledge/`. Документы в них короткие и точные, поэтому исследование на fake-MCP проще, чем на настоящем RAG
- при `dig_through` с полным инвентарём добытый блок пропадает.

Профили возможностей отключают группы tools: `no-vision` (без `inspect`, `scan_area`, `get_known_map`) и `no-docs` (без `search_docs`). Профиль задаётся в сценарии или флагом `--profile`.

## Переезд на реальный MCP

Инструкция для агента или человека, который подключает сервер команды.

1. **Контракт.** Сервер должен реализовать tools из `skills/references/tool-contract.md` (русская версия с примерами в `docs/mcp-contract.md`). Если что-то меняется в контракте, правило синхронизации описано в `docs/mcp-contract.md`.
2. **Конфиг.** В `stand/config.local.yaml`:

   ```yaml
   robot_mcp: real
   real:
     command: [python, -m, team_robot_mcp]   # stdio-сервер
     # url: http://127.0.0.1:8765/mcp        # или streamable HTTP
     real_setup: [python, scripts/place_robot.py]
   ```

3. **`real_setup`.** Скрипт команды, который ставит и включает робота так, как задано в сценарии: позиция и направление `robot`, пустой инвентарь или `robot.inventory`. Runner вызывает его с путём к файлу сценария последним аргументом, уже после сброса региона и постройки сцены. Склад runner наполняет сам через NBT сундука.
4. **Сервер мира.** Реальный робот должен работать в том же мире, который сбрасывает и читает стенд (`stand/server/instance`), иначе судья увидит пустой регион. Если у команды своя сборка, укажите её папку в `server_dir` и проверьте, что RCON включён с паролем из конфига.
5. **Conformance.** `python -m stand.conformance --mcp real`. Сцену проверок (`stand/conformance/scenario.yaml`) готовит `python -m stand.runner prepare --scenario stand/conformance/scenario.yaml`, затем `real_setup`. Все шесть проверок должны пройти: набор tools, конверт ответа, `CANT_PLACE`, `NO_ITEM`, `OUT_OF_RANGE`, `UNKNOWN_ITEM`.
6. **Прогон.** `python -m stand.runner run --scenario s01-wall --agent script`: агент-скрипт без LLM проверяет, что вся цепочка работает с реальным сервером. Затем `suite` с настоящими агентами.

Что меняется в режиме real:

- сценарии с `requires: [fake]` (внедрённые сбои) пропускаются со статусом `SKIPPED`
- action log runner забирает через `get_action_log(1000)`. Если такого tool нет, журнал восстанавливается из вывода агента, но без результатов вызовов, и метрики ошибок по нему не считаются
- профили возможностей не действуют, набор tools определяет сервер команды.

## Если что-то не работает

- **`java ... is Java 25, Forge 1.7.10 needs Java 8`:** поправьте `java_path`.
- **Сервер не отвечает по RCON:** лог консоли в `stand/server/instance/stand-console.log`, лог сервера в `stand/server/instance/logs/latest.log`. Порт 25575 и пароль из конфига.
- **`region ... is not clean even after a full reset`:** шаблон мира испорчен, пересоздайте его командой `python -m stand.server setup --fresh-template` при остановленном сервере.
- **Агент не найден:** `render_cmd` ищет первый элемент команды в PATH, проверьте `claude --version`, `codex --version`, `opencode --version`.
- **Рабочая папка агента** создаётся во временном каталоге системы и удаляется после прогона. Чтобы посмотреть её, добавьте `--keep-workspace`, путь будет в `results.json`.
