# От нуля до сценария

Пять шагов: поднять стенд, подключиться клиентом, собрать робота, поставить и подключить его, выполнить сценарий агентом.
Здесь только порядок и команды, подробности по ссылкам. Команды выполняются из корня репозитория на Windows,
Linux или macOS.

```
клиент Minecraft (вы, творческий режим) ──► сервер стенда localhost:25565
                                              робот OpenComputers ── опрос HTTP :8765 ──┐
Claude Code в demo/workspace ──► адаптер (python -m adapter) ──► мост oc-mcp :8765 ◄──────┘
```

## 1. Поднять стенд

Один раз на машине:

1. Установить [uv](https://docs.astral.sh/uv/), Java 8 (Temurin 8 JRE) и Claude Code.
2. Записать путь к Java 8 в `stand/config.local.yaml`:
   ```yaml
   java_path: C:\Program Files\Eclipse Adoptium\jre-8.0.xxx-hotspot\bin\java.exe
   ```
3. Положить в `stand/server/mods-cache/` jar модов без `url` из `stand/server/mods.yaml` (сборка команды и OC NEI Bridge).
4. Выполнить:
   ```
   uv sync
   uv run oc setup
   ```
   Команда ставит Forge и моды, пишет конфиги сервера и OpenComputers, создаёт мир и карту для Navigation Upgrade.
   Повторный запуск безопасен.

Каждый раз:

```
uv run oc up        # сервер, раздача Lua роботу, рабочая папка агента
uv run oc status    # что запущено и что настроено
```

`uv run oc up --reset` заново ставит площадку и склад, `uv run oc down` всё останавливает.
Подробно: [demo/README.md](../demo/README.md), установка сервера: [stand/README.md](../stand/README.md).

## 2. Подключиться клиентом

1. Лаунчер (например, TLauncher) с Forge 1.7.10.
2. Моды сервера в клиент: `uv run oc client-mods`. Чужие jar в папке модов команда перечислит,
   `--move-foreign` переносит их в `mods-disabled/`.
3. Мультиплеер → `localhost`. Режим уже творческий.
4. `uv run oc give <ваш ник>`: op и предметы для Navigation Upgrade.

Площадка демо: x 85..120, z 85..120, пол на y=63, склад в (95, 64, 105).

## 3. Собрать робота

Из обычных деталей в Electronics Assembler: [docs/robot-build.md](robot-build.md). Коротко:
Navigation Upgrade с картой из `oc give`, затем корпус Tier 3 с Internet Card, Inventory Controller, Crafting,
Geolyzer, Angel, двумя Inventory Upgrade, экраном, клавиатурой и дисководом. Сложность 26 из 32.

## 4. Поставить и подключить робота

1. Поставить робота на площадку, но не на клетку склада (95, 64, 105).
2. ПКМ по роботу, дискета OpenOS в дисковод, кнопка питания, `install` на жёсткий диск, `reboot`.
3. В шелле робота:
   ```
   wget -f http://127.0.0.1:8770/get.lua /home/get.lua
   /home/get.lua
   oc_mcp
   ```
   Робот печатает `oc-mcp polling http://127.0.0.1:8765`. После перезапуска сервера достаточно включить робота:
   `oc_mcp` стартует сам из `/home/.shrc`.

## 5. Выполнить сценарий агентом

```
cd demo/workspace
claude
```

При первом запуске подтвердите доверие к папке и MCP-сервер `robot`. Затем:

1. Проверка связи: `вызови get_status робота`. Позиция должна совпасть с F3 на месте робота.
2. Задача, например:
   > Build a 3x3 wall of cobblestone. Its lower-left block is at (100, 64, 100), it extends along +X and up (+Y), z stays 100. Materials are in the warehouse chest.

Журнал задачи пишется в `demo/workspace/.oc-tasks/`, каждый вызов робота в `demo/logs/action_log.jsonl`,
лог моста в `demo/logs/bridge.log`. Если что-то не так: таблицы «Если не работает» в
[demo/README.md](../demo/README.md#если-не-работает) и [docs/robot-build.md](robot-build.md#если-не-работает).

Сейчас `move_to`, `place_at` и `verify_blocks` в демо смотрят мир через карту-оракул по RCON сервера, а не глазами
робота. Почему так и что с этим делать: [TODO.md](../TODO.md).
