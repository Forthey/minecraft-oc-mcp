# MCP-контракт робота OpenComputers (черновик)

Статус: черновик, с командой не согласован. Дата: 2026-11-10.

Документ описывает, какие MCP-tools агент ожидает от сервера робота. Это предложение к пунктам 2-4 из TASK.md (pathfinding, RAG, транспорт) и к пункту 1 (дамп рецептов NEI).

## Связь со скиллами

Контракт уже используется. Скиллы агента в `skills/` вызывают tools по именам из этого документа, а реакции на ошибки завязаны на коды ошибок отсюда.

Источник правды для скиллов: `skills/references/tool-contract.md` (английский, его читает агент). Этот документ его русская версия для команды с примерами и открытыми вопросами.

**Правило синхронизации.** Любое изменение контракта (новый tool, переименование, новый параметр, новый код ошибки) делается в обоих файлах сразу, и затем проверяются скиллы:

1. Изменить `skills/references/tool-contract.md`.
2. Изменить этот документ.
3. Если менялся список кодов ошибок, обновить `ALL_ERROR_CODES` в `tools/validate_skills.py` и таблицу в `skills/references/error-handling.md`.
4. Поправить скиллы, которые используют изменённый tool (таблица ниже).
5. Поправить fake-MCP стенда: `TOOL_SPECS` в `stand/fake_mcp/dispatch.py` (описание и схема аргументов) и метод в `stand/fake_mcp/sim.py`. Тест `test_tool_specs_match_contract` падает, если набор tools fake-MCP расходится с контрактом.
6. Запустить `.venv/bin/pytest -q` и `.venv/bin/python tools/validate_skills.py`. Тест `test_team_contract_doc_in_sync` падает, если набор tools здесь и в `tool-contract.md` расходится. Валидатор падает, если скилл ссылается на tool или код ошибки, которого нет в контракте.
7. Прогнать `python -m stand.conformance --mcp fake`, а если реальный сервер уже есть, то и `--mcp real`.

### Где используются tools

| Tool | Упоминается в |
|---|---|
| `get_status` | oc-orchestrator, oc-design, oc-build, error-handling |
| `inspect` | error-handling |
| `scan_area`, `get_known_map`, `move`, `drop`, `get_action_log` | пока нигде, оставлены в контракте как запасные |
| `move_to` | oc-build, oc-supply, error-handling |
| `face` | oc-build, oc-supply, oc-verify |
| `dig` | oc-build (как запрещённое действие) |
| `place`, `place_at` | oc-build |
| `use` | oc-verify |
| `list_inventory` | oc-build, oc-supply, error-handling |
| `inspect_container` | oc-supply, oc-build, oc-verify, error-handling |
| `take`, `put` | oc-supply, oc-build, oc-verify, error-handling |
| `equip` | error-handling |
| `craft` | oc-supply, oc-build (как запрещённое действие) |
| `search_items`, `get_recipes` | oc-orchestrator, oc-research, error-handling |
| `get_item` | oc-orchestrator |
| `plan_materials` | oc-orchestrator, oc-supply |
| `search_docs` | oc-orchestrator, oc-research |
| `verify_blocks` | oc-design, oc-build, oc-verify |
| `read_block_info` | oc-verify |
| `stop` | oc-orchestrator, oc-verify |

Таблицу можно пересобрать командой `grep -lw '`<tool>' skills/*/SKILL.md skills/references/*.md`.

## Соглашения

- **Координаты** абсолютные: `[x, y, z]` в мире. В spec.json агента позиции относительные к `origin`, но в вызовы tools всегда попадают абсолютные.
- **Направление** робота `facing`: `north | south | east | west`.
- **Сторона** действия `side`: `front | up | down`. Значения `back | left | right` допустимы, если tool сам разворачивает робота.
- **ID предметов** в формате `mod:name` или `mod:name:meta`, как в дампе NEI, например `IC2:blockGenerator:5`, `minecraft:cobblestone`.
- **Компактный вывод.** Большие результаты по умолчанию отдаются сводкой. Детали запрашиваются через `detail: "full"`, `limit`, `page`. Это главное средство против засорения контекста агента, поэтому сводка по умолчанию обязательна.
- **Высокоуровневые действия.** `move_to` и `place_at` должны сами прокладывать путь. Агент не должен вести робота поблочно.

## Формат ответа

Каждый tool возвращает один и тот же конверт:

```json
{"ok": true, "message": "placed", "data": {}}
```

```json
{"ok": false, "error_code": "NO_PATH", "message": "no route to [15,64,3] with policy avoid", "data": {"from": [12,64,5]}}
```

- `ok`: выполнилось ли действие.
- `error_code`: только при `ok: false`, один из кодов из раздела "Коды ошибок".
- `message`: короткий текст для человека, одна строка.
- `data`: результат, всегда объект. Структура зависит от tool, примеры ниже. Если результат по смыслу список (предметы, рецепты, документы, действия), он лежит в поле объекта: `{"items": [...]}`, `{"recipes": [...]}`, `{"docs": [...]}`, `{"actions": [...]}`.

## Tools

Пометка "(проверить)" означает допущение о возможностях робота, которое нужно подтвердить.

### Состояние

**`get_status()`**

Позиция, направление, энергия, инструмент, сводка инвентаря, позиция склада.

```json
{"pos": [10,64,10], "facing": "north", "energy": 0.9, "tool": {"item": "minecraft:diamond_pickaxe", "durability": 0.7},
 "inventory": {"used": 3, "total": 16, "top": [{"item": "minecraft:cobblestone", "count": 9}]},
 "warehouse": {"pos": [0,64,0], "side": "north"}}
```

**`inspect(side)`**

Блок рядом с роботом: `{"item": "IC2:blockGenerator:5", "name": "Nuclear Reactor"}` или `{"item": "minecraft:air"}`.

**`scan_area(box, detail)`**

Сводка по области. `box`: `{"from": [x,y,z], "to": [x,y,z]}`, `detail`: `summary | full`. В `summary` только счётчики (воздух, твёрдое, жидкость, известные блоки). В `full` список блоков постранично. Дальние блоки без точных ID, потому что geolyzer отдаёт только твёрдость (проверить).

**`get_known_map(box)`**

То, что робот уже помнит о регионе, без сканирования. Формат как у `scan_area` с `detail: full`.

### Движение (пункт 2)

**`move_to(x, y, z, policy)`**

Перемещение с поиском пути. `policy`: `avoid` (ничего не ломать) или `dig_through` (ломать блоки на пути). Ответ: `{"pos": [..], "steps": 14}`. Ошибки: `NO_PATH`, `BLOCKED`, `OUT_OF_RANGE`, `NO_ENERGY`.

**`move(dir, n)`**, **`face(dir)`**

Низкоуровневое движение на `n` блоков (`forward | back | up | down`) и поворот. Запасной вариант.

### Мир

**`dig(side)`**: сломать блок.

**`place(item, side)`**: поставить блок из инвентаря рядом.

**`place_at(x, y, z, item, from?)`**

Подъехать и поставить блок в точку. `from` задаёт сторону подхода. Ошибки: `NO_PATH`, `CANT_PLACE`, `NO_ITEM`, `BLOCKED`.

**`use(side, item?)`**: правый клик по блоку, например переключить рычаг.

### Инвентарь

**`list_inventory(detail)`**: инвентарь робота, `summary | full`.

**`inspect_container(side)`**

Содержимое сундука или машины по слотам:

```json
{"block": "IC2:blockGenerator:5", "slots": [{"slot": 0, "item": "IC2:reactorVent", "count": 1}, {"slot": 1, "item": null}]}
```

**`take(side, item, count, slot?)`**, **`put(side, item, count, slot?)`**

Обмен предметами с контейнером. `slot` нужен для машин (вход, выход, слоты реактора). Ответ: `{"moved": 4}`. Ошибки: `NO_ITEM`, `INVENTORY_FULL`.

**`equip(item)`**, **`drop(item, count)`**: экипировать, выбросить.

### Крафт

**`craft(item, count)`**

Крафт через crafting upgrade. Tool сам раскладывает сетку 3x3 и берёт ингредиенты из инвентаря. Ответ: `{"crafted": 2}`. Ошибки: `NO_ITEM`, `NO_RECIPE`, `INVENTORY_FULL`.

Отдельного tool для машин нет: печь, macerator и т.п. через `put` во входной слот и `take` из выходного.

### Знания (пункты 1 и 3)

**`search_items(query, limit)`**: поиск по индексу предметов, `{"items": [{"item": "...", "name": "...", "mod": "..."}]}`.

**`get_item(id)`**: карточка предмета.

**`get_recipes(item)`**

Рецепты из дампа NEI:

```json
{"recipes": [
 {"type": "crafting_shaped", "output": {"item": "IC2:blockReactorChamber", "count": 1},
  "grid": [[null, "IC2:itemPlates:6", null], ["IC2:itemPlates:6", "IC2:blockMachine", "IC2:itemPlates:6"], [null, "IC2:itemPlates:6", null]],
  "ingredients": {"IC2:itemPlates:6": 4, "IC2:blockMachine": 1}},
 {"type": "machine", "machine": "minecraft:furnace", "output": {"item": "minecraft:iron_ingot", "count": 1},
  "ingredients": {"minecraft:iron_ore": 1}}]}
```

**`plan_materials(item, count, use_inventory)`**

Дерево крафта и то, чего не хватает, с учётом инвентаря робота и склада при `use_inventory: true`:

```json
{"tree": {"item": "IC2:blockReactorChamber", "count": 1, "children": [...]},
 "missing": [{"item": "IC2:itemPlates:4", "count": 2, "craftable": true}]}
```

**`search_docs(query, mod?, limit)`**

Поиск по документации о механиках, мультиблоках, настройке машин. Ответ: `{"docs": [{"doc_id": "...", "title": "...", "snippet": "...", "version": "IC2 2.2.x"}]}`. Без этого tool агенту остаётся только веб-поиск.

### Проверка

**`verify_blocks(expected, page?)`**

Сверка списка `[{"pos": [x,y,z], "item": "..."}]` с миром:

```json
{"checked": 9, "missing": [{"pos": [12,66,9], "item": "minecraft:cobblestone"}], "wrong": [], "next_page": null}
```

В обычном мире через `inspect` с объездом, в тестах через debug card (проверить).

**`read_block_info(side)`**

Состояние машины рядом: энергия, тепло, активность, слоты, например `{"heat": 1200, "max_heat": 10000, "eu_output": 12, "active": true}`. Зависит от драйверов OpenComputers для IC2 и от того, может ли робот обращаться к блоку как компонент (проверить).

### Служебные

**`stop()`**: прервать текущее действие робота. Машины не останавливает.

**`get_action_log(last_n)`**: последние действия робота с результатами. Понадобится для метрик пункта 6.

## Коды ошибок

| Код | Значение |
|---|---|
| `BLOCKED` | Цель или путь заняты, действие невозможно |
| `NO_PATH` | Путь с заданной policy не найден |
| `OUT_OF_RANGE` | Цель слишком далеко или вне загруженной или разрешённой зоны |
| `NO_ITEM` | Нужного предмета нет в инвентаре или контейнере |
| `INVENTORY_FULL` | Нет свободного слота |
| `NO_ENERGY` | Не хватает энергии |
| `TOOL_BROKEN` | Инструмент сломан или отсутствует |
| `CANT_PLACE` | Блок нельзя поставить (нет опоры, не та сторона, защищённая зона) |
| `UNKNOWN_ITEM` | ID или имя предмета не распознаны |
| `NO_RECIPE` | Рецепта нет |
| `TIMEOUT` | Действие не завершилось вовремя |
| `CONNECTION_LOST` | Связь с роботом пропала. Действие могло выполниться, а могло и нет |

Для `TIMEOUT` и `CONNECTION_LOST` важно, чтобы следующий `get_status()` отражал реальное состояние: агент по нему решает, повторять ли действие.

## Открытые вопросы

**Пункт 1 (сборка, NEI)**

- Точные версии IC2 и OpenComputers, они пойдут в `oc-harness.yaml`.
- Формат дампа рецептов: живой API или статичный JSON. Для `get_recipes` и `plan_materials` удобнее статичный.

**Пункт 2 (pathfinding)**

- Реализуемы ли `move_to` с `policy` и `place_at` с выбором стороны подхода.
- Откуда берутся абсолютные координаты: navigation upgrade (ограничен картой) или счисление от стартовой точки.

**Пункт 3 (RAG)**

- Индексировать не только предметы и рецепты, но и тексты о механиках (вики IC2 и OC под версии сборки) для `search_docs`.
- Отдавать версию источника в ответе, агент по ней оценивает достоверность.

**Пункт 4 (транспорт)**

- Где живут `verify_blocks` и `read_block_info`: на роботе, на мосте, через debug card.
- Может ли робот читать состояние машин IC2 так, как компьютер через adapter.
- Как сервер узнаёт, выполнилось ли действие после `CONNECTION_LOST`.
- Разрешён ли internet card доступ к localhost и приватным сетям в конфиге OC.

## История изменений

- 2026-11-10: первая версия, 27 tools, 12 кодов ошибок.
- 2026-11-10: уточнено, что `data` всегда объект и списки лежат в его полях. Пример рецептов приведён к рецептам IC2 2.2.827 (в рецепте есть `ingredients`). В правило синхронизации добавлен fake-MCP стенда.
