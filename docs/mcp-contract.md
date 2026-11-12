# MCP-контракт робота OpenComputers (v2)

Статус: v2, база `oc-mcp`. Дата: 2026-11-11.

Документ описывает, какие MCP-tools ожидает агент. Основа это tools `oc-mcp`, MCP-сервера робота команды (пункт 4 из TASK.md). Сверху наши добавки в мировых координатах, их даёт адаптер поверх `oc-mcp`. Нюансы переезда и вопросы к команде собраны в [real-mcp-notes.md](real-mcp-notes.md).

## Связь со скиллами

Скиллы агента в `skills/` вызывают tools по именам из этого документа, а реакции на ошибки завязаны на коды ошибок отсюда.

Источник правды для скиллов: `agent/skills/references/tool-contract.md` (английский, его читает агент). Этот документ его русская версия для команды с примерами и открытыми вопросами.

**Правило синхронизации.** Любое изменение контракта (новый tool, переименование, новый параметр, новый код ошибки) делается в обоих файлах сразу, и затем проверяются скиллы:

1. Изменить `agent/skills/references/tool-contract.md`.
2. Изменить этот документ.
3. Если менялся список кодов ошибок, обновить `ALL_ERROR_CODES` в `agent/tools/validate_skills.py` и таблицу в `agent/skills/references/error-handling.md`.
4. Поправить скиллы, которые используют изменённый tool (таблица ниже).
5. Поправить fake-MCP стенда: `TOOL_SPECS` в `stand/fake_mcp/dispatch.py` (описание и схема аргументов) и метод в `stand/fake_mcp/sim.py` (tools `oc-mcp`) или `stand/fake_mcp/additions.py` (добавки). Тест `test_tool_specs_match_contract` падает, если набор tools fake-MCP расходится с контрактом.
6. Запустить `uv run pytest -q` и `uv run python agent/tools/validate_skills.py`. Тест `test_team_contract_doc_in_sync` падает, если набор tools здесь и в `tool-contract.md` расходится. Валидатор падает, если скилл ссылается на tool или код ошибки, которого нет в контракте.
7. Прогнать `python -m stand.conformance --mcp fake`, а если реальный сервер уже есть, то и `--mcp real`.

### Где используются tools

Таблица обновляется вместе со скиллами.

| Tool | Упоминается в |
|---|---|
| `get_status` | oc-orchestrator, oc-design, oc-build, error-handling |
| `surroundings` | error-handling |
| `move_to` | oc-build, oc-supply, oc-verify, error-handling |
| `face` | oc-build, oc-supply, oc-verify |
| `place_at` | oc-build |
| `place` | oc-build (запасной путь) |
| `swing` | oc-build (как запрещённое действие), oc-verify (`emergency_off`) |
| `use` | oc-design, oc-verify |
| `inventory_scan` | oc-build, oc-supply, error-handling |
| `storage_scan` | oc-design, oc-build, oc-supply, oc-verify, error-handling |
| `storage_take`, `storage_put` | oc-supply, oc-verify, oc-build (`storage_take` как запрещённое действие), error-handling |
| `equip` | error-handling |
| `craft_recipe`, `craft` | oc-supply, oc-build (как запрещённое действие) |
| `nei_find`, `nei_recipes`, `nei_recipe` | oc-orchestrator, oc-research, error-handling |
| `nei_craft_tree` | oc-orchestrator, oc-supply |
| `nei_machine_plan` | oc-supply |
| `search_docs` | oc-orchestrator, oc-research, error-handling |
| `verify_blocks` | oc-design, oc-build, oc-verify |
| `move`, `turn`, `world_info`, `geo_scan`, `inventory_transfer`, `get_action_log` | пока нигде, оставлены как запасные и для стенда |

## Соглашения

- **Два уровня.** Tools `oc-mcp` работают относительно робота: сторона `side` это `front | up | down`, слоты робота с 1, сетка крафта в слотах робота `1,2,3 / 5,6,7 / 9,10,11`. Добавки работают в мировых координатах `[x, y, z]` и с абсолютными направлениями `north | south | east | west`.
- **ID предметов** в форме NEI `mod:name:damage`, например `minecraft:cobblestone:0`, `IC2:blockMachine:3`. Добавки принимают и `mod:name`, это damage 0.
- **ID рецептов** вида `r7fbebd0471463308` живут только до перезагрузки робота, их нельзя хранить в планах.
- **Высокоуровневые действия.** `move_to`, `place_at` и `verify_blocks` сами прокладывают путь и обходят клетки. Агент не ведёт робота поблочно, `move` и `turn` только запасной путь.

## Формат ответа

Каждый tool возвращает конверт обычным результатом MCP:

```json
{"ok": true, "message": "Placed from slot 1 front: minecraft:cobblestone. 8 left in slot 1.", "data": {"pos": [100, 64, 100]}}
```

```json
{"ok": false, "error_code": "BLOCKED", "message": "moved 2 of 3 blocks forward, blocked: solid", "data": {"pos": [100, 64, 103], "facing": "north"}}
```

- `ok`: выполнилось ли действие.
- `error_code`: только при `ok: false`, один из кодов из раздела "Коды ошибок".
- `message`: для tools `oc-mcp` их текст дословно, для добавок короткий текст в том же стиле.
- `data`: всегда объект. У `nei_*` и `world_info` это их JSON, у `inventory_scan` и `storage_scan` список слотов `{"slots": [{"slot", "count", "name", "label"}]}`. У `move` и `turn` позиция и направление после действия `{"pos", "facing"}`, у `place` и `swing` клетка `{"pos"}`, если позиция робота известна. У добавок своя структура (ниже). У остальных tools `oc-mcp` объект пустой, всё нужное есть в `message`.

Сам `oc-mcp` отвечает текстом, а ошибки отдаёт как JSON-RPC error. Конверт и коды ошибок добавляет наш адаптер.

## Tools

Пометка (oc-mcp) значит, что tool берётся из `oc-mcp` как есть, (добавка) что его даёт адаптер.

### Состояние

**`get_status()`** (добавка)

```json
{"pos": [100, 64, 105], "facing": "north", "inventory": [{"slot": 1, "count": 9, "name": "minecraft:cobblestone:0"}]}
```

Склада здесь нет: агент берёт его из `oc-harness.yaml` (`warehouse: {pos, side}`).

**`world_info()`** (oc-mcp): id и имя робота, `world_id`, с navigation upgrade позиция и направление.

**`surroundings()`** (oc-mcp): шесть соседних блоков относительно направления робота, строками `front: minecraft:stone (solid)`.

**`geo_scan(x, z, y, width, depth, height)`** (oc-mcp): твёрдость блоков бокса в осях робота (x вправо, z вперёд, y вверх), без имён, объём до 64 блоков.

### Движение

**`move_to(x, y, z, policy)`** (добавка)

Перемещение с поиском пути. `policy`: `avoid` (ничего не ломать) или `dig_through` (ломать блоки на пути). Ответ `{"pos": [..], "steps": 14, "dug": []}`. Ошибки: `NO_PATH`, `BLOCKED`, `OUT_OF_RANGE`, `NO_ENERGY`.

**`face(direction)`** (добавка): повернуться на `north | south | east | west`.

**`move(direction, n)`** (oc-mcp): `n` блоков `forward | back | up | down`, остановка у первого препятствия.

**`turn(direction)`** (oc-mcp): `left | right | around`.

### Мир

**`place_at(x, y, z, item, from)`** (добавка)

Подъехать и поставить блок в точку. Слот с предметом находит сам. `from` задаёт сторону подхода. Ответ `{"pos": [..], "slot": 1}`. Ошибки: `NO_PATH`, `CANT_PLACE`, `NO_ITEM`, `UNKNOWN_ITEM`.

**`place(side, slot, sneaky)`** (oc-mcp): поставить блок из слота на сторону.

**`swing(side, sneaky)`** (oc-mcp): сломать блок экипированным инструментом, добыча идёт в инвентарь.

**`use(side, sneaky, duration)`** (oc-mcp): правый клик, например переключить рычаг.

### Инвентарь

**`inventory_scan()`** (oc-mcp): непустые слоты робота строками `slot 1: 9x minecraft:cobblestone:0 (Cobblestone)`.

**`inventory_transfer(from_slot, to_slot, count)`** (oc-mcp): переложить между слотами робота, в слот с другим предметом не кладёт.

**`storage_scan(side)`** (oc-mcp): блок и непустые слоты сундука или машины.

**`storage_take(side, slot, count, robot_slot)`** (oc-mcp): взять из слота хранилища.

**`storage_put(side, robot_slot, count, slot)`** (oc-mcp): положить из слота робота, можно в конкретный слот машины.

**`equip(slot)`** (oc-mcp): поменять местами слот и слот инструмента.

### Крафт

**`craft_recipe(recipe, count)`** (oc-mcp)

Крафт рецепта верстака по id рецепта NEI. Робот сам освобождает сетку, раскладывает ингредиенты из инвентаря и кладёт результат вне сетки. Ошибки: `NO_ITEM` (с перечнем недостающего), `NO_RECIPE`, `INVENTORY_FULL`.

**`craft(count, result_slot)`** (oc-mcp): низкоуровневый крафт того, что уже разложено в сетке.

Машины (печь, macerator) через `nei_machine_plan`, `storage_put` во входные слоты и `storage_take` из выходных.

### Знания

**`nei_find(text, limit, lang)`** (oc-mcp): `{"items": [{"item": "minecraft:chest:0", "label": "Chest", "mod": "minecraft"}], "total": 1}`.

**`nei_recipes(item, usages, category, limit, cursor, lang)`** (oc-mcp)

```json
{"results": [{"item": "minecraft:stick:0", "total": 1, "recipes": [
  {"id": "rf56b51469c3b71ce", "cat": "Shaped Crafting", "catId": "codechicken.nei.recipe.ShapedRecipeHandler",
   "overlay": "crafting", "in": [{"item": "minecraft:planks:0", "n": 2}], "out": [{"item": "minecraft:stick:0", "n": 4}]}]}]}
```

**`nei_recipe(recipe, lang)`** (oc-mcp): рецепт полностью, для верстака сетка `grid: [{"cell", "robotSlot", "item", "count"}]`.

**`nei_craft_tree(item, count, use_inventory, lang)`** (oc-mcp)

Всё дерево крафта за один вызов: `steps` в порядке исполнения (`recipe`, `makes`, `runs`, `in`, `out`, `grid`), `raw` недостающее сырьё, `machinesNeeded`. Учитывает только инвентарь робота, склад агент считает сам.

**`nei_machine_plan(side, recipe, times, lang)`** (oc-mcp): в какие слоты машины класть ингредиенты и откуда забирать результат.

**`search_docs(query, mod, limit)`** (добавка)

Поиск по документации о механиках, мультиблоках, настройке машин: `{"docs": [{"doc_id", "title", "snippet", "version"}]}`. Заглушка до RAG из пункта 3: на стенде по фикстурам, с реальным роботом пока `UNSUPPORTED`.

### Проверка

**`verify_blocks(expected, page)`** (добавка)

Сверка списка `[{"pos": [x,y,z], "item": "..."}]` с миром, 50 записей на страницу:

```json
{"checked": 9, "missing": [{"pos": [101, 66, 100], "item": "minecraft:cobblestone:0"}], "wrong": [], "next_page": null}
```

### Служебные

**`get_action_log(last_n)`** (добавка): последние действия робота с результатами. Нужен для метрик стенда.

## Коды ошибок

| Код | Значение |
|---|---|
| `BLOCKED` | Цель или путь заняты, действие невозможно |
| `NO_PATH` | Путь с заданной policy не найден |
| `OUT_OF_RANGE` | Цель слишком далеко или вне загруженной или разрешённой зоны |
| `NO_ITEM` | Нужного предмета нет в инвентаре или контейнере, или слот пуст |
| `INVENTORY_FULL` | Нет свободного слота |
| `NO_ENERGY` | Не хватает энергии |
| `TOOL_BROKEN` | Инструмента нет, он сломан или не берёт этот блок |
| `CANT_PLACE` | Блок нельзя поставить (нет опоры, клетка занята, предмет не блок) |
| `UNKNOWN_ITEM` | ID или имя предмета не распознаны |
| `NO_RECIPE` | Рецепта нет, id рецепта неизвестен или это не рецепт верстака |
| `TIMEOUT` | Действие не завершилось вовремя |
| `CONNECTION_LOST` | Связь с роботом пропала. Действие могло выполниться, а могло и нет |
| `UNSUPPORTED` | У робота нет компонента или апгрейда, который нужен tool. Сообщение называет его |
| `NO_PROVIDER` | Данных о рецептах сейчас нет: нет игрока с NEI онлайн, и ответа нет в кэше |
| `UNKNOWN` | Текст ошибки не распознан. Агент обращается с ним как с `BLOCKED` |

Для `TIMEOUT` и `CONNECTION_LOST` важно, чтобы следующий `get_status()` отражал реальное состояние: агент по нему решает, повторять ли действие.

## Открытые вопросы

Вопросы к команде по переезду на `oc-mcp` собраны в [real-mcp-notes.md](real-mcp-notes.md). Отдельно здесь:

- **Пункт 2 (pathfinding).** В каком виде будет поиск пути: tool в `oc-mcp`, отдельный MCP или библиотека на роботе. От этого зависит, кто реализует `move_to` и `place_at` после оракул-карты стенда.
- **Пункт 3 (RAG).** Индексировать тексты о механиках (вики IC2 и OC под версии сборки) для `search_docs` и отдавать версию источника в ответе.
- **Пункт 4 (транспорт).** Как `verify_blocks` будет работать в обычной игре без оракула стенда. Как узнать после `CONNECTION_LOST`, выполнилось ли действие.

## История изменений

- 2026-11-10: первая версия, 27 tools, 12 кодов ошибок.
- 2026-11-10: уточнено, что `data` всегда объект и списки лежат в его полях. Пример рецептов приведён к рецептам IC2 2.2.827 (в рецепте есть `ingredients`). В правило синхронизации добавлен fake-MCP стенда.
- 2026-11-11: коды `UNSUPPORTED` и `NO_PROVIDER` для реального MCP (oc-mcp): нет нужного компонента у робота и нет данных NEI без игрока онлайн.
- 2026-11-11: v2, база oc-mcp. 28 tools: tools `oc-mcp` с их именами и аргументами плюс добавки `move_to`, `face`, `place_at`, `get_status`, `verify_blocks`, `search_docs`, `get_action_log`. Удалены `read_block_info`, `stop`, `drop`, `get_known_map` и tools v1 с заменой в `oc-mcp`. Код `UNKNOWN`. Склад перенесён из `get_status` в `oc-harness.yaml`.
- 2026-11-11: правило `data` для сквозных tools `oc-mcp` записано явно. fake-MCP отдаёт ровно те поля, что и адаптер, это проверяет тест паритета `adapter/tests/test_adapter_parity.py`.
