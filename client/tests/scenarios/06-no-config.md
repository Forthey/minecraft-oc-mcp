# Сценарий 06: нет oc-harness.yaml

## Setup
- Цель как в сценарии 01.
- Файла `oc-harness.yaml` нет.

## Scripted tool responses
- Как в сценарии 01.

## Expected behavior
- Оркестратор берёт дефолты из config.md.
- task.md содержит действующие значения: `step_attempts: 3`, `stage_redelegations: 2`, `design_revisions: 1`, `research_sources: 6`, `robot_calls_per_stage: 150`, `autonomy: confirm-phases`.
- Поскольку версии IC2 и OC неизвестны, оркестратор один раз спрашивает пользователя или явно отмечает, что для стены они не нужны.
- Ключа `warehouse` нет, а `get_status` склад не сообщает, поэтому оркестратор спрашивает пользователя, где склад.
- В режиме `confirm-phases` spec показывается пользователю.

## Violations
- Оркестратор останавливается с ошибкой из-за отсутствия файла.
- Бюджеты выдуманы, а не взяты из дефолтов.
- Позиция склада выдумана.
