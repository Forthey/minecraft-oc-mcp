# Сценарий 08: продолжение прерванной задачи

## Setup
- В `.oc-tasks/20261110-1200-ic2-reactor/` есть task.md, spec.json, research/ и journal.md.
- Последние строки журнала: build и verify для `1-structure` со `status=DONE`, build для `2-cooling` со `status=PARTIAL delta=1/2`.
- Пользователь пишет: "Continue building the IC2 reactor."

## Scripted tool responses
- `get_status()` -> `inventory: [{slot: 1, count: 1, name: "IC2:reactorVent:1"}]`
- `storage_scan(front)` у реактора -> `slot 1: 1x IC2:reactorVent:1 (Heat Vent)`

## Expected behavior
- Оркестратор находит существующую задачу и следует Resume.
- Не перезапускает исследование и проектирование.
- Не перестраивает `1-structure`.
- Сверяет состояние через `get_status` и продолжает с этапа `2-cooling`.

## Violations
- Новая папка задачи для той же цели.
- Повтор исследования или этапа `1-structure`.
