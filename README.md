# minecraft-oc-mcp

Управление роботом OpenComputers в Minecraft 1.7.10 через LLM-агента. Lua-клиент на роботе опрашивает локальный MCP-хаб, а адаптер предоставляет агенту инструменты передвижения, взаимодействия с миром, крафта и памяти.

[Презентация](https://docs.google.com/presentation/d/1OLj-rejppY4s1J5yrgDrOB08oZKG0iBLtZwdPM41fmI/edit?usp=sharing)

## Запуск

1. Установить зависимости:
   ```bash
   uv sync
   ```
2. В `opencomputers.cfg` добавить `"allow ip:127.0.0.1"` перед `"deny private"`. На робота поставить Internet Card, Geolyzer, Inventory Controller и Navigation Upgrade.
3. Запустить хаб и оставить процесс работать:
   ```bash
   scripts/hub.sh
   ```
4. В терминале робота установить и запустить клиент:
   ```text
   wget -f http://127.0.0.1:8765/get.lua /home/get.lua
   /home/get.lua
   oc_mcp
   ```
5. Подключить в MCP-клиенте `robot` по адресу `http://127.0.0.1:8765/mcp`. Для памяти запустить `memory_mcp.server` с тем же `MEMORY_DB`, что у хаба.
6. Установить скиллы агента:
   ```bash
   mkdir -p ~/.explyt/skills
   cp -R agent/skills/* ~/.explyt/skills/
   ```

Дополнительно: [настройка и переменные окружения](docs/GUIDE.md), [сборка робота](docs/robot-build.md), [Java pathfinding](pathfinding/java/README.md).
