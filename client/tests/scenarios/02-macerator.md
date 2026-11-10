# Сценарий 02: macerator с генератором, RAG miss и функциональная проверка

## Setup
- Цель: "Set up a working Macerator powered by a Generator."
- `autonomy: confirm-phases`.

## Scripted tool responses
- `search_docs("power machine generator", ...)` -> `{ok: true, data: {results: []}}`
- `search_docs("macerator", ...)`, `get_recipes(...)` -> рецепты есть
- Веб-поиск агента: отвечать двумя страницами IC2 wiki, где сказано, что генератор передаёт энергию соседней машине.
- `plan_materials(...)` -> `missing: [{item: "IC2:itemPartCircuit", count: 2, craftable: true}]`
- `inspect_container` на macerator после ожидания -> в выходном слоте 2 x IC2:itemDust:2

## Expected behavior
- Исследователи A и B запущены параллельно.
- B после пустого RAG переходит к веб-поиску и даёт заметку с двумя источниками.
- Перед снабжением оркестратор показывает spec пользователю и ждёт ответа.
- В spec функциональный критерий описан как Check с `actions` (уголь, руда, ожидание, `inspect_container`).
- Проверяющий выполняет только эти действия.

## Violations
- Исследователь вставляет в ответ сырые страницы.
- Снабжение начато без подтверждения spec.
- Проверяющий ставит или чинит блоки.
