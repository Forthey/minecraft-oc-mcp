# E2E-стенд

Стенд проверяет агента со скиллами из `agent/skills/` от начала до конца: агент получает цель, через MCP управляет роботом, в мире Minecraft появляется постройка, судья сверяет её с ожиданием и считает метрики.

Сценарии и что из них показывать на демо: [docs/stand-scenarios.md](../docs/stand-scenarios.md).

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
uv sync                                   # из корня репозитория, .venv в корне
uv run python -m stand.server setup --pin
```

`setup` проверяет Java, ставит Forge, скачивает моды по `stand/server/mods.yaml` (IC2, OpenComputers, NEI с зависимостями), пишет конфиги, создаёт шаблон мира, затем правит `OpenComputers.cfg` (доступ к 127.0.0.1, `ignorePower`, `limitFlightHeight`) и пишет карту для Navigation Upgrade. Последние два шага требуют остановленного сервера. Повторный запуск безопасен. Если мод не скачивается, положите jar в `stand/server/mods-cache/` руками.

Команды `python -m stand...` ниже запускаются из корня репозитория через `uv run` или из активированного `.venv`.

## Команды

```bash
python -m stand.server start | stop | status           сервер
python -m stand.runner run --scenario s01-wall --agent claude [--repeat 3] [--profile no-docs]
python -m stand.runner run --scenario s01-wall --agent claude --repeat 2 --memory-chain   память переходит между повторами
python -m stand.runner run --scenario s09-memory --agent claude --memory-from stand/runs/<прогон>
python -m stand.runner suite --agents claude,codex [--scenarios s01-wall,s07-relative] [--repeat 3]
python -m stand.runner prepare --scenario s03-obstacle  сбросить регион и поставить сцену (для ручной проверки)
python -m stand.runner judge --scenario s03-obstacle    оценить текущий мир без агента
python -m stand.runner report                           пересобрать stand/runs/summary.md
python -m stand.conformance --mcp fake | real           контрактные проверки MCP-сервера
```

`run` и `suite` сами запускают сервер, если он не отвечает.

**Агенты** описаны в `stand/agents.yaml`: `claude`, `claude-haiku`, `codex`, `opencode` и `script`. Модель задаётся флагом в команде, поэтому для другой модели добавьте запись с другим именем. Агент `script` не использует LLM: он выполняет эталонное решение `stand/scenarios/<id>/script.json` и нужен, чтобы бесплатно проверить, что стенд работает целиком. Решение есть у каждого сценария. Шаг с полем `"expect": "<код>"` должен вернуть эту ошибку, так записаны ожидаемые отказы вроде `NO_PATH` в s03 и `CONNECTION_LOST` в s05.

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
| `memory.db` | база памяти агента (сервер `memory`) после прогона, её можно передать следующему через `--memory-from` |

`stand/runs/summary.md` собирает таблицу сценарий на агент: доля PASS по повторам, медианы времени, вызовов и стоимости, ложные успехи, нарушения.

## Метрики

**Статус прогона:**

- `PASS`: судья принял постройку
- `FAIL`: не принял
- `ASKED`: агент закончил вопросом пользователю, не заявив успех
- `TIMEOUT`: вышло время сценария, дерево процессов агента убито
- `CRASH`: агент упал с ненулевым кодом, и судья не принял постройку
- `SKIPPED`: сценарий требует fake-MCP, а стенд работает с реальным.

**Память** (`memory` в `results.json`, строка «Память» в report.md). Каждый прогон получает сервер `memory` с базой
в рабочей папке агента, по умолчанию пустой, чтобы прогоны оставались повторяемыми. Сценарий может положить в неё
факты заранее (`memory.seed`) и убрать склад из `oc-harness.yaml` (`memory.hide_warehouse`), так устроен s09-memory.
`--memory-from <папка прогона>` начинает с базы прошлого прогона, `--memory-chain` передаёт её между повторами.
Поля: `used` (агент открыл сессию), `agent_sessions`, `pois_added`, `episodes_added`, `facts_added` и
`warehouse_remembered` (в базе есть сундук на месте склада). Агент `script` память не использует.

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

Fake-MCP эмулирует контракт v2: tools `oc-mcp` (робот команды) и наши добавки. Тексты ответов tools `oc-mcp` скопированы из его Lua-кода (`stand/fake_mcp/texts.py`), модель робота в `stand/fake_mcp/sim.py`, добавки в `stand/fake_mcp/additions.py`, NEI в `stand/fake_mcp/nei.py`. От настоящего робота fake-MCP отличается так:

- робот перемещается мгновенно, может висеть в воздухе и в мире не виден
- блоки ставятся без опоры, гравитации нет
- склад, инвентарь и слоты машин живут в памяти (сундук склада в мире наполняется только для наглядности)
- `use` ничего не делает
- `geo_scan` отдаёт твёрдость без шума, у настоящего геолайзера она шумит тем сильнее, чем дальше блок
- `move_to`, `place_at` и `verify_blocks` знают весь регион (оракул-карта), настоящий робот видит только соседние блоки
- NEI (`nei_*`, `craft_recipe`) работает по фикстурам `stand/knowledge/`, а не по NEI клиента игрока. `nei_machine_plan` кладёт входы в слоты машины с 1 подряд и берёт выход из следующего слота, настоящий мод берёт слоты из окна машины
- `search_docs` ищет по коротким и точным документам фикстур, поэтому исследование на fake-MCP проще, чем на настоящем RAG
- при `swing` или `dig_through` с полным инвентарём добытый блок пропадает.

Профили возможностей: `no-vision` (без `surroundings` и `geo_scan`), `no-docs` (без `search_docs`) и `no-nei` (tools `nei_*` и `craft_recipe` отвечают `NO_PROVIDER`, как OC NEI Bridge без игрока онлайн). Профиль задаётся в сценарии или флагом `--profile`.

## Переезд на реальный MCP

Инструкция для агента или человека, который подключает сервер команды. Реальный сервер робота это `oc-mcp` команды, а добавки контракта (`move_to`, `place_at`, `verify_blocks`, коды ошибок, журнал) даёт наш адаптер поверх него. Адаптер и реальный режим стенда (робот в шаблоне мира, прогрев кэша NEI) это подпроекты B и C, нюансы и вопросы к команде в `docs/real-mcp-notes.md`.

1. **Контракт.** Сервер должен реализовать tools из `agent/skills/references/tool-contract.md` (русская версия с примерами в `docs/mcp-contract.md`). Если что-то меняется в контракте, правило синхронизации описано в `docs/mcp-contract.md`.
2. **Конфиг.** В `stand/config.local.yaml`, для `oc-mcp` через наш адаптер:

   ```yaml
   robot_mcp: real
   oc_mcp_dir: .        # каталог с bridge/, в монорепо это корень (значение по умолчанию)
   real:
     command: ["{python}", -m, adapter, --oc-mcp, "{oc_mcp_dir}/bridge/server.py", --world-id, stand,
               --map, "stand.adapter_map:oracle", --map-arg, "scenario={scenario}", --log, "{action_log}"]
     real_setup: [python, scripts/place_robot.py]
   ```

   Адаптер (`adapter/`) запускает `oc-mcp` дочерним процессом, переводит его тексты в конверт с кодами ошибок и добавляет `move_to`, `place_at`, `verify_blocks` и остальные добавки контракта. Карта для них берётся из снимка мира стенда (`stand/adapter_map.py`). Runner подставляет `{python}`, `{oc_mcp_dir}`, `{scenario}` (сценарий прогона без ожидаемого ответа) и `{action_log}`, а журнал действий читает из файла, который пишет адаптер. Сервер команды без адаптера подключается так же, через `command` или `url`, тогда журнал берётся через `get_action_log`.

3. **`real_setup`.** Скрипт команды, который ставит и включает робота так, как задано в сценарии: позиция и направление `robot`, пустой инвентарь или `robot.inventory`. Runner вызывает его с путём к файлу сценария последним аргументом, уже после сброса региона и постройки сцены. Склад runner наполняет сам через NBT сундука.
4. **Сервер мира.** Реальный робот должен работать в том же мире, который сбрасывает и читает стенд (`stand/server/instance`), иначе судья увидит пустой регион. Если у команды своя сборка, укажите её папку в `server_dir` и проверьте, что RCON включён с паролем из конфига.
5. **Conformance.** `python -m stand.conformance --mcp real`. Сцену проверок (`stand/conformance/scenario.yaml`) готовит `python -m stand.runner prepare --scenario stand/conformance/scenario.yaml`, затем `real_setup`. Все семь проверок должны пройти: набор tools, конверт ответа, `place` в занятую клетку даёт `BLOCKED`, `storage_take` из пустого слота даёт `NO_ITEM`, `OUT_OF_RANGE`, `UNKNOWN_ITEM`, `nei_find` отвечает или даёт `NO_PROVIDER`.
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
