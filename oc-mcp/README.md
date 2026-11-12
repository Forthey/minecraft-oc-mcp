# oc-mcp

MCP-мост между ИИ-агентом и роботом OpenComputers (Minecraft 1.7.10).
Python-процесс работает MCP-сервером через stdio и одновременно слушает HTTP на `127.0.0.1:8765`;
Lua-скрипт на роботе раз в секунду забирает команды (`GET /poll`) и отправляет результат (`POST /result`).

## Быстрый старт

### 1. Разрешить роботу ходить на localhost

По умолчанию Internet Card **не пускает на 127.0.0.1 и локальную сеть** — без этого робот молча
не достучится до моста. Закройте Minecraft и в `.minecraft/config/opencomputers.cfg` найдите
`filteringRules` в секции `internet`. Добавьте `"allow ip:127.0.0.1"` **перед** `"deny private"`:

```
filteringRules=[
  removeme,
  "allow ip:127.0.0.1",
  "deny private",
  "deny bogon",
  "allow default"
]
```

Порядок важен: правила проверяются сверху вниз, и `deny private` срабатывает раньше, если
поставить разрешение ниже. Конфиг читается только при старте игры. Если мост запущен на другой
машине, вместо `127.0.0.1` разрешите её LAN-адрес.

### 2. Моды

В `.minecraft/mods` нужны OpenComputers и, для тулов `nei_*`, NotEnoughItems + OC NEI Bridge + UniMixins.
Без NEI-моста тулы `nei_*` просто отключатся на роботе, остальные работают.

### 3. Робот

Нужны: Internet Card, Inventory Controller, Crafting Upgrade, Geolyzer, апгрейд инвентаря
(крафт требует ≥12 слотов). Желательно Navigation Upgrade — без него нет координат и направления.

### 4. Скопировать скрипты на робота

`lua/oc_mcp.lua` и папку `lua/oc_mcp/` положить в один каталог робота. Проще всего — прямо в сейв,
**при закрытой игре** (OC держит файловую систему в памяти и перезапишет внешние правки):

```
.minecraft/saves/<мир>/opencomputers/<uuid диска робота>/home/
```

### 5. Подключить мост к MCP-клиенту

Нужен Python 3.11+, внешних зависимостей нет. Пути — **абсолютные**: GUI-клиенты на macOS запускаются
с урезанным PATH и не находят голый `python3` (`spawn python3 ENOENT`).

```json
{
  "mcpServers": {
    "opencomputers": {
      "command": "/absolute/path/to/python3.11+",
      "args": ["/absolute/path/to/oc-mcp/bridge/server.py", "--world-id", "my-world"]
    }
  }
}
```

Параметры `server.py`: `--port` (по умолчанию 8765), `--host`, `--log-file` (по умолчанию `bridge/bridge.log`),
`--world-id` — идентификатор мира для памяти агента (тул `world_info`). Мост должен быть запущен **ровно один**:
второй экземпляр упадёт с `Address already in use`.

### 6. Запустить

1. Перезапустить MCP-серверы в клиенте.
2. Запустить игру, на роботе выполнить `oc_mcp` (или `oc_mcp http://адрес:порт`, если мост не на localhost/8765).
3. Попросить агента вызвать любой тул, например `inventory_scan`.

### Если не работает

- **«OpenComputers did not respond»** — робот не опрашивает мост. Смотрите `oc_mcp.log` рядом со скриптом на роботе
  (в сейве он появится после сохранения мира): `poll failed` — сеть/`filteringRules`, нет `poll ok` — скрипт не запущен.
- **«unknown command type: X»** — на роботе старая копия скриптов, скопируйте заново.
- **«tool X is disabled: ...»** — у робота нет нужного компонента; причина в тексте ошибки и в `oc_mcp.log`.
- **Клиент видит 0 тулов** — мост падает при старте; запустите вручную:
  `printf '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n' | <python> bridge/server.py --port 8799`.
- Запросы моста пишутся в `bridge/bridge.log`; в stdout мост ничего, кроме MCP, не печатает.

## Новый тул

1. Python: класс-наследник `Tool` в `bridge/tools.py` и добавить его в `TOOLS`. Схема выводится из аннотаций:
   `x: int` — обязательное, `x: int = 1` — со значением по умолчанию, `x: int | None` — необязательное без значения,
   ограничения через `Annotated[int, Range(1, 64)]` и `Literal[...]`.
2. Lua: файл `lua/oc_mcp/tools/<name>.lua`, возвращающий
   `{requires = {...}, available = function(robot) ... end, run = function(robot, args) ... return ok, text end}`,
   и имя в `lua/oc_mcp/tools/init.lua`.

Списки тулов на мосту и роботе не синхронизируются: тул, отключённый на роботе, мост всё равно покажет.

## Ограничения

- Нет авторизации: HTTP-эндпоинт только для локальной машины/сети.
- Очередь команд в памяти и теряется при перезапуске моста.
- Робот должен быть включён, с питанием, в загруженном чанке.
