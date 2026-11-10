# oc-mcp

## Запуск bridge

Требуется Python 3.9+ без внешних зависимостей:

```sh
python3 bridge/server.py
```

Процесс является MCP-сервером через stdio и одновременно слушает HTTP на `127.0.0.1:8765`.

## Запуск Lua-клиента

Скопируйте `lua/oc_mcp.lua` и папку `lua/oc_mcp/` в один каталог компьютера OpenComputers (например, `/home`) и запустите:

```lua
oc_mcp [http://адрес:порт]
```

Новый tool: файл `lua/oc_mcp/tools/<name>.lua`, возвращающий `{requires = {...}, available = function(robot) ... end, run = function(robot, args) ... end}`, и его имя в `lua/oc_mcp/tools/init.lua`.

Скрипт раз в секунду делает `GET /poll`, выполняет команду и отправляет `POST /result`. В зависимости от версии OpenComputers loopback-адрес может быть недоступен из Internet Card; тогда замените `bridge` в скрипте на LAN-адрес машины, где запущен Python.

MCP-клиент должен запускать bridge как stdio-сервер, например:

```json
{
  "mcpServers": {
    "opencomputers": {
      "command": "python3",
      "args": ["/absolute/path/to/oc-mcp/bridge/server.py"]
    }
  }
}
```
