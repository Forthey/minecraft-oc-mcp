# Интерактивное демо: Claude Code (haiku) управляет настоящим роботом

```
клиент Minecraft ──► сервер стенда (Forge 1.7.10, localhost:25565, RCON 25575)
                         ▲  робот OpenComputers: oc_mcp.lua опрашивает 127.0.0.1:8765
Claude Code (haiku) ──► адаптер (python -m adapter) ──► мост oc-mcp (:8765)
  demo/workspace          карта-оракул: снимок региона через RCON
```

Мост (`bridge/`) и адаптер (`adapter/`) поднимает сам Claude Code из `workspace/.mcp.json`, отдельно их запускать не надо.
Всё остальное делает CLI `oc` (`demo/cli.py`). Он работает из любого каталога и на любой ОС:

| Команда | Что делает |
|---|---|
| `uv run oc setup` | Один раз: Forge, моды, конфиги сервера и OpenComputers, шаблон мира, карта для Navigation Upgrade |
| `uv run oc up [--reset]` | Сервер Minecraft, раздача Lua роботу (:8770, в фоне), сборка `demo/workspace`. `--reset` заново ставит площадку и склад |
| `uv run oc down` | Останавливает сервер и раздачу Lua |
| `uv run oc status` | Что запущено и что настроено |
| `uv run oc give <ник>` | Op и предметы для Navigation Upgrade игроку онлайн |
| `uv run oc client-mods [--dest DIR] [--move-foreign]` | Копирует моды сервера в клиент |
| `uv run oc workspace` | Пересобирает `demo/workspace` (подтянуть правки скиллов) |

## Подготовка (один раз на машине)

1. `uv sync` в корне репозитория: `.venv` со всеми пакетами и командой `oc`.
2. Java 8: путь к `java.exe` в `stand/config.local.yaml` (`java_path: ...`), подробно в [stand/README.md](../stand/README.md).
3. `uv run oc setup --pin`. Получится Forge 1.7.10-10.13.4.1614 и моды в `stand/server/instance`. При остановленном
   сервере `setup` ещё правит `config/OpenComputers.cfg` (`"allow ip:127.0.0.1"` перед `"deny private"`,
   `ignorePower=true`, `limitFlightHeight=256`) и пишет в мир карту масштаба 1 с центром (0, 0) для Navigation Upgrade.
   Повторный запуск безопасен. Четыре мода из сборки команды скачать нельзя, их jar кладутся в
   `stand/server/mods-cache/` руками (список в `stand/server/mods.yaml`, у них `url: null`).
4. Клиент: TLauncher (или другой лаунчер) с Forge 1.7.10 и теми же модами, что на сервере:
   `uv run oc client-mods`. По умолчанию это `%APPDATA%\.minecraft\mods`. Если там лежат чужие jar (например,
   моды Fabric 1.21), команда их перечислит, а `--move-foreign` переносит их в `mods-disabled/` рядом.

Площадка `scenario.yaml`: регион x 85..120, z 85..120, сундук-склад в (95, 64, 105) с булыжником,
камнем, досками и стеклом.

## Запуск

```
uv run oc up            # первый раз или после правок площадки: uv run oc up --reset
```

### Один раз: собрать робота

Мультиплеер → `localhost` (режим уже творческий), затем пошагово по [docs/robot-build.md](../docs/robot-build.md):
Navigation Upgrade с картой стенда, сборка в Electronics Assembler из обычных деталей, установка OpenOS,
подключение к мосту. Робот на площадке переживает `oc up --reset`, если не стоит на клетке склада (95, 64, 105).

### Каждый раз: агент

```
cd demo/workspace
claude            # модель haiku задана в .claude/settings.json; или: claude --model haiku
```

При первом запуске подтвердите доверие к папке (trust dialog) и, если спросит, MCP-сервер `robot`.
Без этого разрешения из `.claude/settings.json` не применяются, и каждый вызов робота будет спрашивать подтверждение.

Первый промпт для проверки связи: `вызови get_status робота`. В ответе позиция совпадает с F3
у робота. Потом сама задача, например:

> Build a 3x3 wall of cobblestone. Its lower-left block is at (100, 64, 100), it extends along +X and up (+Y), z stays 100. Materials are in the warehouse chest.

Смотрите на стройку в клиенте, стоя вне площадки. Журнал задачи пишется в `workspace/.oc-tasks/`,
каждый вызов робота в `demo/logs/action_log.jsonl`, лог моста в `demo/logs/bridge.log`, раздачи Lua в `demo/logs/lua_server.log`.

## Если не работает

| Симптом | Что делать |
|---|---|
| `CONNECTION_LOST: robot does not respond` | На роботе не запущен `oc_mcp`. Смотрите `/home/oc_mcp.log` на роботе (`edit /home/oc_mcp.log`): `poll failed` значит сеть или `filteringRules` |
| `get_status` без координат или они не совпадают с F3 | Navigation Upgrade скрафчен не с картой из `oc give` |
| В Claude Code нет tools `robot` | Сервер Minecraft должен работать до запуска `claude`: карта-оракул подключается к RCON. Проверка: `uv run oc status`, затем `/mcp` в Claude Code |
| `Address already in use` в логе моста | Уже запущен другой `claude` с этим MCP: мост на 8765 может быть только один |
| Клиент падает при входе: `IndexOutOfBoundsException` в `RenderGlobal` | `options.txt` общий с 1.21: `renderDistance` больше 16 роняет 1.7.10. Поставлено 12, копия с 32 лежит в `options.txt.bak-1.21` |
| Клиент не пускает на сервер (mod mismatch) или падает | В папке модов клиента лежат чужие jar (например, Fabric 1.21): `uv run oc client-mods --move-foreign` |
