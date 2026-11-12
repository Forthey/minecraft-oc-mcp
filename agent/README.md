# OC agent skills

Набор markdown-скиллов, которые учат локального агента (Claude Code, opencode, Codex с любой моделью) управлять роботом OpenComputers в Minecraft 1.7.10 через MCP. Агент получает высокоуровневую цель вроде "построй ядерный реактор IC2", сам исследует, как это устроено, пишет план постройки и выполняет его через субагентов с проверками на каждом этапе.

MCP-контракт робота для команды: [docs/mcp-contract.md](../docs/mcp-contract.md). Он синхронизирован с `agent/skills/references/tool-contract.md`, менять оба файла вместе.

Сценарии e2e-стенда и что из них показывать на демо: [docs/stand-scenarios.md](../docs/stand-scenarios.md).

E2E-стенд с метриками (сервер Minecraft, fake-MCP, судья, runner, переезд на реальный MCP): [stand/README.md](../stand/README.md).

## Структура

Пути ниже относительно `agent/`. Адаптер, стенд и остальное описаны в [корневом README](../README.md).

```
skills/
  oc-orchestrator/   точка входа: фазы, журнал, делегирование, эскалация
  oc-research/       исследование: RAG, веб, кросс-проверка, research note
  oc-design/         план постройки spec.json (использует оркестратор)
  oc-supply/         материалы со склада и крафт
  oc-build/          стройка одного этапа
  oc-verify/         структурная и функциональная проверка, аварийное выключение
  references/        контракт tools, обработка ошибок, конфиг, схема spec, примеры трасс
    examples/        oc-harness.yaml и пример spec.json
tools/               структурный валидатор скиллов
tests/               тесты валидатора и поведенческие сценарии (tests/scenarios)
```

Скиллы ссылаются на `references/` относительными путями (`../references/...`), поэтому при установке каталог `references/` должен лежать рядом с каталогами скиллов.

## Установка

Пути ниже нужно сверить с документацией конкретной версии агента.

- **Claude Code**: скопировать содержимое `skills/` в `.claude/skills/` проекта или в `~/.claude/skills/`.
- **opencode**: скопировать в каталог скиллов opencode (`.opencode/skill/` проекта или глобальный), если версия поддерживает `SKILL.md`. Иначе подключить `oc-orchestrator/SKILL.md` как инструкцию агента, а остальные файлы оставить рядом.
- **Codex**: скопировать в каталог скиллов Codex (`~/.codex/skills/`), если версия поддерживает скиллы. Иначе сослаться на `skills/oc-orchestrator/SKILL.md` из `AGENTS.md`.

Если агент не умеет запускать субагентов, оркестратор переходит в последовательный режим (секция Fallback without subagents).

Дальше:

1. Подключить MCP-сервер робота в конфиге агента. Скиллы ждут tools из [skills/references/tool-contract.md](skills/references/tool-contract.md). MCP команды `oc-mcp` подключается не напрямую, а через адаптер: `python -m adapter --oc-mcp bridge/server.py` из корня репозитория (флаги в `python -m adapter --help` и в [stand/README.md](../stand/README.md)). Адаптер отдаёт tools `oc-mcp` в конверте контракта и добавляет недостающие. Без `--map` добавки, которым нужна карта мира (`move_to`, `place_at`, `verify_blocks`), отвечают `UNSUPPORTED`.
2. Положить `oc-harness.yaml` в корень проекта, из которого запускается агент (пример в [skills/references/examples/oc-harness.yaml](skills/references/examples/oc-harness.yaml)), и заполнить версии модов и позицию склада.
3. Добавить `.oc-tasks/` и `.oc-knowledge/` в `.gitignore`, если проект в git.

## Проверка скиллов

Структурная проверка (frontmatter, длина, ссылки, имена tools и коды ошибок против контракта, схема spec, формат журнала):

```bash
uv sync                                      # из корня репозитория
uv run pytest -q agent/tests
uv run python agent/tools/validate_skills.py
```

Поведенческая проверка идёт по сценариям из `tests/scenarios/`. Каждый сценарий состоит из секций Setup, Scripted tool responses, Expected behavior и Violations. Прогон вручную:

1. Запустить агента со скиллами без подключённого MCP робота.
2. Дать ему цель из Setup и сказать, что вызовы tools робота он пишет текстом, а ответы приходят от человека.
3. Отвечать на вызовы по Scripted tool responses.
4. Сверить поведение с Expected behavior и отметить каждое нарушение из Violations.
5. Записать результат в `tests/scenarios/RESULTS.md`.
