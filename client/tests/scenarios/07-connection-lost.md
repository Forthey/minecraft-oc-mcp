# Сценарий 07: CONNECTION_LOST посреди этапа

## Setup
- Роль: строитель, этап `1-wall` из 9 блоков.

## Scripted tool responses
- Первые 4 `place_at` -> `{ok: true}`
- 5-й `place_at` -> `{ok: false, error_code: "CONNECTION_LOST"}`
- следующий `get_status()` -> `{ok: true}`, позиция рядом с 5-м блоком
- `inspect` на 5-ю позицию -> блок уже стоит (действие выполнилось)

## Expected behavior
- Строитель не повторяет 5-й `place_at` вслепую.
- Сначала `get_status`, потом проверка факта установки (`inspect` или `verify_blocks`).
- Продолжает с 6-го блока, delta считает по реальному состоянию.

## Violations
- Повторный `place_at` в ту же точку сразу после `CONNECTION_LOST`.
- delta в отчёте не совпадает с фактом.
