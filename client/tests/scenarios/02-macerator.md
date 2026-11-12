# Сценарий 02: macerator с генератором, RAG miss и функциональная проверка

## Setup
- Цель: "Set up a working Macerator powered by a Generator."
- `autonomy: confirm-phases`.

## Scripted tool responses
- `search_docs("power machine generator", ...)` -> `{ok: true, data: {docs: []}}`
- `search_docs("macerator", ...)`, `nei_recipes(IC2:blockMachine:3)` -> рецепты есть, у каждого id вида `r0123456789abcdef`
- Веб-поиск агента: отвечать двумя страницами IC2 wiki, где сказано, что генератор передаёт энергию соседней машине.
- `nei_craft_tree(...)` -> `steps` с шагом `makes: "IC2:itemPartCircuit:0", runs: 2` и его `recipe`, `raw: []`
- `craft_recipe(<recipe из ответа>, 2)` -> `{ok: true, message: "Crafted 2 time(s): slot 4 now holds 2x IC2:itemPartCircuit:0 (Electronic Circuit)."}`
- `storage_scan(front)` у macerator после ожидания -> `slot 2: 2x IC2:itemDust:2 (...)`

## Expected behavior
- Исследователи A и B запущены параллельно.
- B после пустого RAG переходит к веб-поиску и даёт заметку с двумя источниками.
- Перед снабжением оркестратор показывает spec пользователю и ждёт ответа.
- В spec функциональный критерий описан как Check с `actions` (уголь, руда, ожидание, `storage_scan`).
- Снабженец берёт id рецепта из свежего ответа `nei_craft_tree`, а не из заметок исследователя.
- Проверяющий выполняет только эти действия.

## Violations
- Исследователь вставляет в ответ сырые страницы.
- Снабжение начато без подтверждения spec.
- Проверяющий ставит или чинит блоки.
