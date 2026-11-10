# Сценарий 01: стена 3x3, пропуск исследования

## Setup
- Цель пользователя: "Build a 3x3 cobblestone wall in front of you."
- `oc-harness.yaml` из skills/references/examples/, `autonomy: auto`.
- В `.oc-tasks/` пусто.

## Scripted tool responses
- `get_status()` -> `{ok: true, data: {pos: [10,64,10], facing: "north", energy: 0.9, warehouse: [0,64,0]}}`
- `plan_materials(minecraft:cobblestone, 9, true)` -> `{ok: true, data: {missing: []}}`
- `inspect_container(...)` на складе -> 64 x minecraft:cobblestone
- все `take`, `place_at` -> `{ok: true}`
- `verify_blocks(...)` -> `{ok: true, data: {missing: [], wrong: []}}`

## Expected behavior
- Оркестратор не запускает исследователей и пишет причину в decisions.md.
- spec.json валиден по схеме, один этап, `emergency_off: null`.
- Снабженец, строитель, проверяющий запускаются последовательно, проверяющий не тот же субагент, что строитель.
- В журнале строки по формату для supply, build, verify.
- Итоговое сообщение пользователю короткое, с путём к journal.md.

## Violations
- Оркестратор сам вызывает `place_at` или `take`.
- Пропущена фаза проверки.
- Строки журнала не подходят под формат.
