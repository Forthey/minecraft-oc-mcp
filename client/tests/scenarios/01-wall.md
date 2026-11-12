# Сценарий 01: стена 3x3, пропуск исследования

## Setup
- Цель пользователя: "Build a 3x3 cobblestone wall in front of you."
- `oc-harness.yaml` из skills/references/examples/, `autonomy: auto`.
- В `.oc-tasks/` пусто.

## Scripted tool responses
- Склад в `oc-harness.yaml`: `warehouse: {pos: [6,64,10], side: east}`.
- `get_status()` -> `{ok: true, message: "At [10, 64, 10] facing north, 0 inventory slots used.", data: {pos: [10,64,10], facing: "north", inventory: []}}`
- `nei_craft_tree(minecraft:cobblestone, 9, true)` -> `{ok: true, data: {steps: [], raw: [{item: "minecraft:cobblestone:0", n: 9}], machinesNeeded: []}}`
- `storage_scan(front)` у склада -> `{ok: true, message: "Block: minecraft:chest\nStorage has 27 slots.\nslot 1: 64x minecraft:cobblestone:0 (Cobblestone)"}`
- `storage_take(front, 1, 9)` -> `{ok: true, message: "Took items from front slot 1."}`
- все `move_to`, `face`, `place_at` -> `{ok: true}`
- `verify_blocks(...)` -> `{ok: true, data: {checked: 9, missing: [], wrong: [], next_page: null}}`

## Expected behavior
- Оркестратор не запускает исследователей и пишет причину в decisions.md.
- spec.json валиден по схеме, один этап, `emergency_off: null`.
- Снабженец, строитель, проверяющий запускаются последовательно, проверяющий не тот же субагент, что строитель.
- В журнале строки по формату для supply, build, verify.
- Итоговое сообщение пользователю короткое, с путём к journal.md.

## Violations
- Оркестратор сам вызывает `place_at` или `storage_take`.
- Пропущена фаза проверки.
- Строки журнала не подходят под формат.
