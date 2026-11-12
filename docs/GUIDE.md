# От нуля до сценария

Пять шагов: поднять стенд, подключиться клиентом, собрать робота, поставить и подключить его, выполнить сценарий
агентом. Здесь только порядок и команды, подробности по ссылкам. Команды выполняются из корня репозитория
и работают на Windows, Linux и macOS. Агент на выбор: Claude Code, Codex или opencode.

```
клиент Minecraft (вы, творческий режим) -----> сервер стенда localhost:25565
                                                 робот OpenComputers
                                                   |  опрашивает HTTP :8765
агент в demo/workspace --MCP--> адаптер --MCP--> мост oc-mcp :8765
```

## 1. Поднять стенд

Один раз на машине:

1. Установить [uv](https://docs.astral.sh/uv/), Java 8 (Temurin 8 JRE) и одного из агентов: Claude Code, Codex
   или opencode.
2. Записать путь к Java 8 в `stand/config.local.yaml`:
   ```yaml
   java_path: C:\Program Files\Eclipse Adoptium\jre-8.0.xxx-hotspot\bin\java.exe
   ```
3. Положить в `stand/server/mods-cache/` jar модов, у которых в `stand/server/mods.yaml` стоит `url: null`.
   Это моды из сборки команды и OC NEI Bridge, скачать их автоматически нельзя.
4. Выполнить:
   ```
   uv sync
   uv run oc setup
   ```
   `oc setup` ставит Forge и моды, пишет конфиги сервера и OpenComputers, создаёт мир и карту для Navigation Upgrade.
   Повторный запуск безопасен.

Каждый раз:

```
uv run oc up        # сервер, раздача Lua роботу, рабочая папка агента
uv run oc status    # что запущено и что настроено
```

`uv run oc up --reset` заново ставит площадку и склад, `uv run oc down` всё останавливает.
Подробнее: [demo/README.md](../demo/README.md), установка сервера: [stand/README.md](../stand/README.md).

## 2. Подключиться клиентом

1. Нужен лаунчер с Forge 1.7.10, например TLauncher.
2. Скопировать моды сервера в клиент: `uv run oc client-mods`. Если в папке модов есть чужие jar, команда их
   перечислит, а с флагом `--move-foreign` перенесёт их в `mods-disabled/`.
3. В игре: Мультиплеер, адрес `localhost`. Режим уже творческий.
4. `uv run oc give <ваш ник>`: op и предметы для Navigation Upgrade.

Площадка демо: x 85..120, z 85..120, пол на y=63, склад в (95, 64, 105).

## 3. Собрать робота

Робот собирается из обычных деталей в Electronics Assembler, пошагово в [docs/robot-build.md](robot-build.md).
Коротко: сначала Navigation Upgrade с картой из `oc give`, затем корпус Tier 3 с Internet Card, Inventory
Controller, Crafting, Geolyzer, Angel, двумя Inventory Upgrade, экраном, клавиатурой и дисководом.
Сложность сборки 26 из 32.

## 4. Поставить и подключить робота

1. Поставить робота на площадку, но не на клетку склада (95, 64, 105).
2. Открыть робота (ПКМ), вставить дискету OpenOS в дисковод, нажать кнопку питания. В шелле выполнить `install`,
   выбрать жёсткий диск, затем `reboot`.
3. В шелле робота:
   ```
   wget -f http://127.0.0.1:8770/get.lua /home/get.lua
   /home/get.lua
   oc_mcp
   ```
   Робот печатает `oc-mcp polling http://127.0.0.1:8765`. После перезапуска сервера достаточно включить робота:
   `oc_mcp` запустится сам из `/home/.shrc`.

## 5. Выполнить сценарий агентом

`oc up` собирает `demo/workspace` сразу для трёх агентов: скиллы из `agent/skills`, инструкции, конфиг MCP-сервера
`robot` и `oc-harness.yaml` (склад и версии модов). Агент запускается так:

| Агент | Команда | Что он берёт из `demo/workspace` |
|---|---|---|
| Claude Code | `uv run oc agent claude` | `.mcp.json`, `.claude/skills`, `CLAUDE.md`, `.claude/settings.json` (модель haiku, tools робота без подтверждений) |
| Codex | `uv run oc agent codex` | `AGENTS.md` и `skills/`. MCP-сервер `robot` приходит флагами `-c` вместе с таймаутом вызова 600 с |
| opencode | `uv run oc agent opencode` | `opencode.json`, `.opencode/skills`, `AGENTS.md` |

Claude Code и opencode можно запускать и напрямую из папки (`cd demo/workspace`, затем `claude` или `opencode`):
всё нужное лежит в файлах. Codex так не получится: проектный конфиг в непроверенной папке он не читает, поэтому
без `oc agent codex` он не увидит MCP-сервер робота.

Аргументы после `--` передаются агенту как есть:

```
uv run oc agent claude -- --model sonnet
uv run oc agent codex -- -m <модель> -a never      # -a never: не спрашивать подтверждения на каждый вызов
uv run oc agent opencode -- --model <провайдер>/<модель>
```

При первом запуске агент спросит, доверять ли папке. Claude Code ещё спросит про MCP-сервер `robot`, Codex
по умолчанию спрашивает подтверждение на вызовы tools. Дальше:

1. Проверить связь: `вызови get_status робота`. Позиция должна совпасть с F3, если встать на место робота.
2. Дать задачу, например:
   > Build a 3x3 wall of cobblestone. Its lower-left block is at (100, 64, 100), it extends along +X and up (+Y), z stays 100. Materials are in the warehouse chest.

Другой MCP-клиент подключается так же: stdio-сервер с командой и аргументами из `demo/workspace/.mcp.json`,
инструкция из `demo/workspace/AGENTS.md`, скиллы из `demo/workspace/skills/`.

Агент ведёт память между задачами (MCP-сервер `memory`): склад, построенное, правила игрока и уроки. Посмотреть её
можно командой `uv run oc memory`, подробнее в [demo/README.md](../demo/README.md#память-между-задачами).

Журнал задачи пишется в `demo/workspace/.oc-tasks/`, каждый вызов робота в `demo/logs/action_log.jsonl`,
лог моста в `demo/logs/bridge.log`. Если что-то пошло не так, смотрите таблицы "Если не работает"
в [demo/README.md](../demo/README.md#если-не-работает) и [docs/robot-build.md](robot-build.md#если-не-работает).

Пока `move_to`, `place_at` и `verify_blocks` в демо смотрят на мир через карту-оракул по RCON сервера, а не
глазами робота. Почему так и что с этим делать, описано в [TODO.md](../TODO.md).
