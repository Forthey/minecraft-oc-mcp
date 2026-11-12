# Сборка робота

Гайд для OpenComputers 1.8.10 (Minecraft 1.7.10) на сервере стенда. Игрок играет в творческом режиме и берёт
детали из творческой вкладки OpenComputers. Сам робот собирается из обычных деталей в Electronics Assembler,
готовый творческий робот (Creatix, корпус Creative) не нужен.

Слоты, сложность и рецепты сверены с jar мода: `RobotTemplate`, `Settings.deviceComplexityByTier`, драйверы деталей
и `default.recipes`. Если версия OpenComputers в `stand/server/mods.yaml` поменяется, их стоит перепроверить.

## Что нужно заранее

1. Стенд поднят: один раз `uv run oc setup`, затем `uv run oc up`. В выводе `uv run oc status` должны быть строки
   `opencomputers config  ok` и `navigation map  map_<id>`.
2. Клиент с модами сервера (`uv run oc client-mods`) зашёл на `localhost`.
3. Выполнена команда `uv run oc give <ник>`: она выдаёт op, карту стенда, 4 золота, компас, бутылку воды и верстак.

## Что робот должен уметь и какой детали это требует

Каждый tool робота (`robot/oc_mcp/tools/*.lua`) включается, только если у робота есть нужные компоненты.
Без них tool отвечает `tool X is disabled: missing component: ...`, а адаптер отдаёт агенту код `UNSUPPORTED`.

| Деталь | Без неё |
|---|---|
| Internet Card | Робот не связывается с мостом, не работает ничего |
| Navigation Upgrade | Нет координат и направления: `get_status`, `move_to`, `face`, `place_at` отвечают `UNSUPPORTED` |
| Inventory Upgrade | Робот не может держать предметы: не работают стройка, склад и крафт |
| Inventory Controller Upgrade | Нет `storage_scan`, `storage_take`, `equip`, `craft_recipe` и имён предметов в `inventory_scan` |
| Crafting Upgrade | Нет `craft` и `craft_recipe` |
| Geolyzer | Нет `surroundings`, `geo_scan` и имени блока в `storage_scan` |
| Angel Upgrade | Робот ставит блок, только если у целевой клетки есть опора (земля или поставленный блок) |
| Screen (Tier 1), Keyboard, Graphics Card | Нельзя ничего набрать в шелле робота |
| Disk Drive | Нечем поставить OpenOS с дискеты |

Для tools `nei_*` отдельная деталь не нужна: мод OC NEI Bridge даёт компонент `nei` всем компьютерам, но ему
нужно не меньше 1 МБ памяти. Hover Upgrade тоже не нужен: `oc setup` поднимает `limitFlightHeight` до 256.

## Шаг 1. Navigation Upgrade

Navigation Upgrade отдаёт координаты относительно центра карты, из которой его скрафтили. Карта из `oc give`
имеет центр (0, 0) и масштаб 1, поэтому координаты робота совпадают с F3 на расстоянии до 128 блоков от (0, 0)
по каждой оси, площадка демо в эти пределы входит. Новая карта или карта из творческой вкладки не подойдут:
координаты будут смещены.

Возьмите в творческой вкладке OpenComputers два **Microchip (Tier 2)** и скрафтите на верстаке:

| | | |
|---|---|---|
| Gold Ingot | Compass | Gold Ingot |
| Microchip (Tier 2) | карта из `oc give` | Microchip (Tier 2) |
| Gold Ingot | Water Bottle | Gold Ingot |

## Шаг 2. Детали

Из творческой вкладки OpenComputers:

- **Electronics Assembler**;
- **Computer Case (Tier 3)**;
- **Central Processing Unit (CPU) (Tier 3)**;
- **Memory (Tier 3.5)**, 2 шт.;
- **Hard Disk Drive (Tier 2)**;
- **EEPROM (Lua BIOS)**. Если во вкладке есть только пустой EEPROM, положите его на верстак вместе
  с OpenComputers Manual в любом порядке;
- **Internet Card**, **Graphics Card (Tier 1)**;
- **Inventory Controller Upgrade**, **Crafting Upgrade**, **Angel Upgrade**, **Inventory Upgrade** (2 шт.);
- **Geolyzer**, **Screen (Tier 1)**, **Keyboard**, **Disk Drive**;
- дискета **OpenOS**. Если её нет во вкладке, положите на верстак Floppy Disk и OpenComputers Manual в любом порядке.

Плюс Navigation Upgrade из шага 1.

## Шаг 3. Сборка

Поставьте Electronics Assembler вне площадки демо (x 85..120, z 85..120), например у (80, 64, 100).
Питание не нужно: `oc setup` включает `ignorePower=true`.

Откройте сборщик (ПКМ) и положите Computer Case (Tier 3) в его главный слот, появятся слоты корпуса. Если навести
курсор на слот, подходящие предметы в инвентаре подсветятся. В слот с римской цифрой N влезает деталь уровня N
и ниже.

| Слоты корпуса Tier 3 | Что положить | Сложность |
|---|---|---|
| Карты: T3, T2, T2 | Internet Card, Graphics Card (Tier 1) | 2 + 1 |
| CPU: T3 | CPU (Tier 3) | 0 |
| Память: T3, T3 | Memory (Tier 3.5) в оба слота, всего 2 МБ | 3 + 3 |
| EEPROM | EEPROM (Lua BIOS) | 0 |
| Диски: T3, T2 | Hard Disk Drive (Tier 2) | 2 |
| Апгрейды: T3, T3, T3 | Inventory Controller, Crafting, Navigation | 2 + 2 + 2 |
| Апгрейды: T2, T2, T2 | Angel, Geolyzer, Inventory Upgrade | 2 + 1 + 1 |
| Апгрейды: T1, T1, T1 | Screen (Tier 1), Keyboard, Inventory Upgrade | 1 + 1 + 1 |
| Контейнеры: T3, T2, T2 | Disk Drive в любой из них, остальные по желанию (ниже) | 2 |

Сложность получается 26 из 32, сборщик показывает её строкой `Complexity: 26/32`. Для корпуса Tier 3 с CPU Tier 3
предел равен 32, и при сумме выше предела сборщик не запустится. Считается так: корпус, CPU и EEPROM в сложность
не входят, деталь уровня N стоит N, контейнер уровня N стоит 2N. Disk Drive в роботе считается контейнером
уровня 1: он стоит 2 и ставится в контейнерный слот, а не в слот апгрейда.

Два Inventory Upgrade дают 32 слота инвентаря, по 16 каждый. Сетка крафта занимает слоты 1-3, 5-7 и 9-11.
Если хотите потом добавлять апгрейды без пересборки, положите в свободный контейнерный слот
**Upgrade Container (Tier 2)**, сложность станет 30. В собранном роботе в этот контейнер можно вставить любой
апгрейд уровня 2 и ниже.

Нажмите кнопку запуска, дождитесь конца сборки и заберите робота из выходного слота. Собранного робота изменить
нельзя, его можно только разобрать в Disassembler, и детали при этом могут сломаться. Поэтому проверьте раскладку
до запуска.

## Шаг 4. Поставить робота и установить OpenOS

1. Поставьте робота на площадку, например на (96, 64, 105), но **не** на клетку склада (95, 64, 105):
   `oc up --reset` ставит туда сундук. В остальном сброс площадки робота не трогает. А вот полный сброс мира
   из шаблона (`prepare --fresh` или неудачный сброс региона) удаляет и робота.
2. Откройте робота (ПКМ), положите дискету OpenOS в слот дисковода и нажмите кнопку питания.
3. OpenOS загрузится с дискеты. Выполните `install`, выберите жёсткий диск и подтвердите. После `reboot` робот
   загружается с диска, дискету можно забрать.

## Шаг 5. Подключить робота к мосту

`uv run oc up` печатает эти же команды. В шелле робота:

```
wget -f http://127.0.0.1:8770/get.lua /home/get.lua
/home/get.lua
oc_mcp
```

Установщик скачивает клиент oc-mcp в `/home` и дописывает `oc_mcp` в `/home/.shrc`, так что после перезапуска
сервера достаточно нажать кнопку питания. Робот печатает `oc-mcp polling http://127.0.0.1:8765` и, пока агент
не запущен, молча опрашивает мост. Остановить скрипт: Ctrl+Alt+C.

## Шаг 6. Проверить

- Откройте `/home/oc_mcp.log` на роботе (`edit /home/oc_mcp.log`): у каждого tool должно стоять
  `tool <name>: enabled`. Строка `disabled (missing component: X)` значит, что деталь X забыта (таблица в начале).
- Запустите агента: `uv run oc agent claude`, `uv run oc agent codex` или `uv run oc agent opencode`. Попросите
  `вызови get_status робота`. Позиция должна совпасть с F3, если встать на место робота, а `facing` с направлением,
  куда смотрит робот.

## Если не работает

| Симптом | Причина |
|---|---|
| Сборщик не запускается, сложность выше 32 | Лишние детали или детали слишком высокого уровня. Сверьтесь с таблицей шага 3 |
| Сборщик не принимает деталь в слот | Уровень детали выше уровня слота: апгрейды T2 идут только в слоты T2 и T3 |
| Сборка стоит на месте | Нет питания. В `uv run oc status` должно быть `opencomputers config ok`, иначе остановите сервер (`oc down`) и выполните `oc setup` |
| Робот не загружается: `no bios found; install a configured EEPROM` | EEPROM пустой или его нет: нужен EEPROM (Lua BIOS) |
| Робот не загружается: `no bootable medium found` | OpenOS не установлена на диск, и дискеты в дисководе нет |
| `get_status` без координат | Нет Navigation Upgrade |
| Координаты не совпадают с F3 | Navigation Upgrade скрафчен не с картой из `oc give` |
| `ERROR: Internet Card is required` в `oc_mcp.log` | Нет Internet Card |
| `poll failed` в `oc_mcp.log` | Агент не запущен (мост поднимается вместе с ним) или в конфиге OpenComputers нет доступа к 127.0.0.1 (`oc status`) |
| `place_at` не ставит блоки без опоры | Нет Angel Upgrade: стройте снизу вверх |
