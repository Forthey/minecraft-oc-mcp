# Интерактивное демо: Claude Code (haiku) управляет настоящим роботом

```
клиент Minecraft ──► сервер стенда (Forge 1.7.10, localhost:25565, RCON 25575)
                         ▲  робот OpenComputers: oc_mcp.lua опрашивает 127.0.0.1:8765
Claude Code (haiku) ──► адаптер (python -m adapter) ──► мост oc-mcp (:8765)
  demo/workspace          карта-оракул: снимок региона через RCON
```

Мост (`bridge/`) и адаптер (`adapter/`) поднимает сам Claude Code из `workspace/.mcp.json`, отдельно их запускать не надо.
Lua-скрипты робота раздаёт `serve_lua.py` прямо из `robot/`.

## Подготовка (один раз на машине)

Команды из корня репозитория.

1. `uv sync`: `.venv` в корне со всеми пакетами.
2. Java 8 и сервер стенда: `stand/config.local.yaml` с `java_path`, затем
   `uv run python -m stand.server setup --pin` (подробно в [stand/README.md](../stand/README.md)).
   Получится Forge 1.7.10-10.13.4.1614 и моды в `stand/server/instance`.
3. В `stand/server/instance/config/OpenComputers.cfg` добавить `"allow ip:127.0.0.1"` перед `"deny private"`,
   `ignorePower=true`, `limitFlightHeight=256`.
4. При остановленном сервере: `uv run python demo/make_nav_map.py`. Пишет в мир карту `map_0` масштаба 1
   с центром (0, 0) для Navigation Upgrade.
5. `uv run python demo/setup_workspace.py`: собирает `demo/workspace/` (скиллы из `agent/skills`, `.mcp.json`
   с сервером `robot`, `oc-harness.yaml`, `CLAUDE.md`, `.claude/settings.json` с моделью haiku и разрешениями
   на tools робота). Каталог в `.gitignore`, повторный запуск подтягивает правки скиллов.
6. Клиент: те же моды, что на сервере, в `%APPDATA%\.minecraft\mods\1.7.10\` (и `mods\ic2\`).

Площадка `scenario.yaml`: регион x 85..120, z 85..120, сундук-склад в (95, 64, 105) с булыжником,
камнем, досками и стеклом.

## Запуск

```powershell
cd demo
.\start.ps1            # сервер + раздача Lua; .\start.ps1 -Reset заново ставит площадку и склад
```

### Один раз: собрать робота (TLauncher, версия Forge 1.7.10)

1. Мультиплеер → `localhost`. Режим уже творческий. Отойдите от площадки: робот и склад стоят у (96, 64, 105).
2. `.\give_map.ps1 -Nick <ваш ник>`: выдаёт op, карту `filled_map 1 0`, золото, компас, бутылку воды
   и верстак. Возьмите в творческой вкладке OpenComputers **Microchip (Tier 2)** ×2 и скрафтите
   **Navigation Upgrade**: золото, компас, золото / чип, карта, чип / золото, бутылка, золото.
   Карта из творческого инвентаря или новая не подойдёт: координаты будут смещены.
3. Робот: в творческой вкладке OpenComputers возьмите готового **Robot** (имя Creatix). В нём уже есть
   CPU T3, память, HDD T3, дискета OpenOS, видеокарта, Internet Card, экран, клавиатура, геолайзер,
   4 Inventory Upgrade, Inventory Controller, Crafting, Hover Upgrade, Upgrade Container и Card Container.
   Нет Navigation и Angel Upgrade.
4. Поставьте робота на (96, 64, 105), например, или в любое свободное место площадки.
   Поставить можно только после `start.ps1 -Reset`: сброс площадки удаляет робота.
5. ПКМ по роботу. Положите Navigation Upgrade в слот **Upgrade Container**. Включите робота
   (загрузится OpenOS с дискеты), выполните `install`, выберите жёсткий диск, затем `reboot`.
   Без Angel Upgrade робот не ставит блоки «в воздух»: только если рядом с целевой клеткой есть
   опора (земля или уже поставленный блок). Для стен и площадок снизу вверх это не мешает.
6. В шелле робота:
   ```
   wget -f http://127.0.0.1:8770/get.lua /home/get.lua
   /home/get.lua
   oc_mcp
   ```
   Робот пишет `oc-mcp polling http://127.0.0.1:8765`. Окно можно закрыть, скрипт работает дальше.
   Пока Claude Code не запущен, мост не слушает порт: робот тихо повторяет опрос.
   После перезапуска сервера робот выключен: включите и снова выполните `oc_mcp`.

### Каждый раз: агент

```powershell
cd demo\workspace
claude            # модель haiku задана в .claude/settings.json; или: claude --model haiku
```

При первом запуске подтвердите доверие к папке (trust dialog) и, если спросит, MCP-сервер `robot`.
Без этого разрешения из `.claude/settings.json` не применяются, и каждый вызов робота будет спрашивать подтверждение.

Первый промпт для проверки связи: `вызови get_status робота`. В ответе позиция совпадает с F3
у робота. Потом сама задача, например:

> Build a 3x3 wall of cobblestone. Its lower-left block is at (100, 64, 100), it extends along +X and up (+Y), z stays 100. Materials are in the warehouse chest.

Смотрите на стройку в клиенте, стоя вне площадки. Журнал задачи пишется в `workspace/.oc-tasks/`,
каждый вызов робота в `logs/action_log.jsonl`, лог моста в `logs/bridge.log`.

## Если не работает

| Симптом | Что делать |
|---|---|
| `CONNECTION_LOST: robot does not respond` | На роботе не запущен `oc_mcp`. Смотрите `/home/oc_mcp.log` на роботе (`edit /home/oc_mcp.log`): `poll failed` значит сеть или `filteringRules` |
| `get_status` без координат или они не совпадают с F3 | Navigation Upgrade скрафчен не с `filled_map 1 0` |
| В Claude Code нет tools `robot` | Сервер Minecraft должен работать до запуска `claude`: карта-оракул подключается к RCON. Проверка: `/mcp` в Claude Code |
| `Address already in use` в логе моста | Уже запущен другой `claude` с этим MCP: мост на 8765 может быть только один |
| Клиент падает при входе: `IndexOutOfBoundsException` в `RenderGlobal` | `options.txt` общий с 1.21: `renderDistance` больше 16 роняет 1.7.10. Поставлено 12, копия с 32 лежит в `options.txt.bak-1.21` |
| Клиент не пускает на сервер (mod mismatch) или падает | В `%APPDATA%\.minecraft\mods\` лежат моды Fabric 1.21. Если Forge 1.7.10 на них падает, временно перенесите их в другую папку |
