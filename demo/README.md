# Интерактивное демо: агент управляет настоящим роботом

Агент (Claude Code, Codex или opencode) управляет роботом OpenComputers на сервере стенда, а вы смотрите на стройку
из клиента игры. Пошаговый путь от нуля до сценария: [docs/GUIDE.md](../docs/GUIDE.md). Здесь подробности по демо.

```
клиент Minecraft -----> сервер стенда (Forge 1.7.10, localhost:25565, RCON 25575)
                          робот OpenComputers: oc_mcp.lua опрашивает 127.0.0.1:8765
                                                            |
агент в demo/workspace --MCP--> адаптер (python -m adapter) --MCP--> мост oc-mcp (:8765)
                                карта-оракул: снимок региона через RCON
```

Адаптер (`adapter/`) и мост (`bridge/`) запускает сам агент по конфигу MCP из `demo/workspace`, отдельно их
запускать не надо. Всё остальное делает CLI `oc` (`demo/cli.py`). Он работает из любого каталога и на любой ОС:

| Команда | Что делает |
|---|---|
| `uv run oc setup` | Один раз: Forge, моды, конфиги сервера и OpenComputers, шаблон мира, карта для Navigation Upgrade |
| `uv run oc up [--reset]` | Запускает сервер Minecraft и раздачу Lua роботу (порт 8770, в фоне), собирает `demo/workspace`. С `--reset` заново ставит площадку и склад |
| `uv run oc down` | Останавливает сервер и раздачу Lua |
| `uv run oc status` | Показывает, что запущено и что настроено |
| `uv run oc give <ник>` | Выдаёт игроку онлайн op и предметы для Navigation Upgrade |
| `uv run oc client-mods [--dest DIR] [--move-foreign]` | Копирует моды сервера в клиент |
| `uv run oc agent <claude, codex или opencode> [-- аргументы]` | Собирает `demo/workspace` и запускает в ней агента |
| `uv run oc workspace` | Пересобирает `demo/workspace`, например чтобы подтянуть правки скиллов |
| `uv run oc memory [--reset]` | Что агент запомнил между задачами; `--reset` стирает память |

## Подготовка (один раз на машине)

1. `uv sync` в корне репозитория: `.venv` со всеми пакетами и командой `oc`.
2. Java 8: путь к `java.exe` в `stand/config.local.yaml` (`java_path: ...`), подробнее в [stand/README.md](../stand/README.md).
3. Агент: Claude Code, Codex или opencode, команда `claude`, `codex` или `opencode` должна находиться в PATH.
4. `uv run oc setup`. Команда ставит Forge 1.7.10-10.13.4.1614 и моды в `stand/server/instance`. При остановленном
   сервере она ещё правит `config/OpenComputers.cfg` (`"allow ip:127.0.0.1"` перед `"deny private"`,
   `ignorePower=true`, `limitFlightHeight=256`) и пишет в мир карту масштаба 1 с центром (0, 0) для Navigation
   Upgrade. Повторный запуск безопасен. Флаг `--pin` нужен только при смене модов: он вписывает новые sha256
   в `mods.yaml`. Четыре мода из сборки команды скачать нельзя, их jar кладутся в `stand/server/mods-cache/`
   руками (у них в `stand/server/mods.yaml` стоит `url: null`).
5. Клиент: лаунчер (например, TLauncher) с Forge 1.7.10 и модами сервера, их копирует `uv run oc client-mods`.
   По умолчанию моды кладутся в `%APPDATA%\.minecraft\mods`. Если там лежат чужие jar (например, моды Fabric 1.21),
   команда их перечислит, а с `--move-foreign` перенесёт в соседнюю папку `mods-disabled/`.

Площадка из `scenario.yaml`: регион x 85..120, z 85..120, сундук-склад в (95, 64, 105) с булыжником, камнем,
досками и стеклом.

## Запуск

```
uv run oc up            # в первый раз или после правок площадки: uv run oc up --reset
```

### Один раз: собрать робота

В игре: Мультиплеер, адрес `localhost` (режим уже творческий). Дальше пошагово по
[docs/robot-build.md](../docs/robot-build.md): Navigation Upgrade с картой стенда, сборка в Electronics Assembler
из обычных деталей, установка OpenOS и подключение к мосту. Робот переживает `oc up --reset`, если не стоит
на клетке склада (95, 64, 105).

### Каждый раз: агент

```
uv run oc agent claude      # или: uv run oc agent codex, uv run oc agent opencode
```

`oc up` и `oc agent` собирают `demo/workspace` сразу для трёх агентов:

| Агент | Что берёт из `demo/workspace` | Запуск без `oc agent` |
|---|---|---|
| Claude Code | `.mcp.json`, `.claude/skills`, `CLAUDE.md`, `.claude/settings.json`: модель haiku и разрешение на tools робота | `cd demo/workspace`, затем `claude` |
| Codex | `AGENTS.md` и `skills/`. MCP-сервер `robot` приходит флагами `-c` с таймаутом вызова tool 600 с | Нет: проектный конфиг в непроверенной папке Codex не читает |
| opencode | `opencode.json`, `.opencode/skills`, `AGENTS.md` | `cd demo/workspace`, затем `opencode` |

Аргументы после `--` передаются агенту без изменений, например `uv run oc agent claude -- --model sonnet`,
`uv run oc agent codex -- -m <модель> -a never` или `uv run oc agent opencode -- --model <провайдер>/<модель>`.

При первом запуске агент спросит, доверять ли папке. Claude Code ещё спросит про MCP-сервер `robot`: без этого
разрешения из `.claude/settings.json` не применяются, и каждый вызов робота потребует подтверждения. Codex
по умолчанию сам спрашивает подтверждение на вызовы tools, флаг `-a never` это отключает.

Первый запрос для проверки связи: `вызови get_status робота`. Позиция в ответе должна совпасть с F3, если встать
на место робота. Затем сама задача, например:

> Build a 3x3 wall of cobblestone. Its lower-left block is at (100, 64, 100), it extends along +X and up (+Y), z stays 100. Materials are in the warehouse chest.

Смотрите на стройку в клиенте, стоя вне площадки. Журнал задачи пишется в `demo/workspace/.oc-tasks/`, каждый вызов
робота в `demo/logs/action_log.jsonl`, лог моста в `demo/logs/bridge.log`, лог раздачи Lua в `demo/logs/lua_server.log`.

### Память между задачами

Кроме `robot`, агент получает MCP-сервер `memory` (`memory/`, база `demo/memory.db`). Как им пользоваться, оркестратор
читает в `agent/skills/references/memory.md`:

- на старте задачи: `world_info` робота даёт `world_id` и `robot_id`, затем `open` и `brief`. Агент получает
  известные места рядом (склад, машины, прошлые постройки), закреплённые правила игрока и уроки прошлых задач;
- уроки попадают подагентам в `Known failures`, рядом со строками `tried.md`;
- в конце задачи агент сохраняет склад и построенное, а если задача чему-то научила, один урок;
- если сказать агенту факт («склад теперь в (90, 64, 90)», «не копай у базы»), он запишет его сразу.

Склад из `oc-harness.yaml` главнее памяти. Память нужна, когда склада в yaml нет, и для всего остального.
Посмотреть, что запомнено: `uv run oc memory`, стереть: `uv run oc memory --reset`.

## Если не работает

| Симптом | Что делать |
|---|---|
| `CONNECTION_LOST` с текстом `OpenComputers did not respond within ...` | На роботе не запущен `oc_mcp`. Откройте `/home/oc_mcp.log` на роботе (`edit /home/oc_mcp.log`): `poll failed` значит, что робот не достучался до моста |
| `get_status` без координат или координаты не совпадают с F3 | Navigation Upgrade скрафчен не с картой из `oc give` |
| У агента нет tools `robot` | Адаптер упал при старте. В Claude Code ошибку покажет `/mcp`, в Codex `codex mcp list`. Лог моста в `demo/logs/bridge.log`. Сервер Minecraft для старта адаптера не нужен |
| `move_to`, `place_at`, `verify_blocks` отвечают `stand server is not reachable over RCON` | Карта-оракул обращается к серверу стенда по RCON: выполните `uv run oc up`. Агента перезапускать не нужно |
| `Address already in use` в логе моста | Уже запущен другой агент с этим MCP-сервером: мост на порту 8765 может быть только один |
| Клиент падает при входе: `IndexOutOfBoundsException` в `RenderGlobal` | `options.txt` клиента достался от новой версии игры: при `renderDistance` больше 16 Minecraft 1.7.10 падает. Поставьте 12 или меньше |
| Клиент не пускает на сервер (mod mismatch) или падает | В папке модов клиента лежат чужие jar (например, Fabric 1.21): `uv run oc client-mods --move-foreign` |
