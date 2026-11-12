# Сборка робота

Гайд для OpenComputers 1.8.10 (Minecraft 1.7.10) на сервере стенда. Игрок в творческом режиме и берёт детали
из творческой вкладки OpenComputers, а сам робот собирается из обычных деталей в Electronics Assembler.
Готовый творческий робот (Creatix, корпус Creative) не нужен.

Слоты, сложность и рецепты ниже сверены с jar мода (`RobotTemplate`, `Settings.deviceComplexityByTier`, драйверы деталей,
`default.recipes`). Если версия OpenComputers в `stand/server/mods.yaml` поменяется, их стоит перепроверить.

## Что нужно заранее

1. Стенд поднят: `uv run oc setup` (один раз), затем `uv run oc up`. `uv run oc status` должен показать
   `opencomputers config  ok` и `navigation map  map_<id>`.
2. Клиент с модами сервера (`uv run oc client-mods`) зашёл на `localhost`.
3. `uv run oc give <ник>`: op, карта стенда, 4 золота, компас, бутылка воды, верстак.

## Что робот должен уметь и какой детали это требует

Каждый tool робота (`robot/oc_mcp/tools/*.lua`) включается, только если у робота есть нужные компоненты.
Иначе tool отвечает `tool X is disabled: missing component: ...`, а адаптер выдаёт `UNSUPPORTED`.

| Деталь | Без неё |
|---|---|
| Internet Card | Робот не достучится до моста, не работает ничего |
| Navigation Upgrade | Нет координат и направления: `get_status`, `move_to`, `face`, `place_at` отвечают `UNSUPPORTED` |
| Inventory Upgrade | Робот не может держать предметы: нет стройки, склада и крафта |
| Inventory Controller Upgrade | Нет `storage_scan`, `storage_take`, `equip`, `craft_recipe` и имён предметов в `inventory_scan` |
| Crafting Upgrade | Нет `craft` и `craft_recipe` |
| Geolyzer | Нет `surroundings`, `geo_scan` и имени блока в `storage_scan` |
| Angel Upgrade | Робот ставит блок, только если у целевой клетки есть опора (земля или поставленный блок) |
| Screen (Tier 1), Keyboard, Graphics Card | Нельзя ничего набрать в шелле робота |
| Disk Drive | Нечем поставить OpenOS с дискеты |

Tools `nei_*` дополнительного железа не требуют: мод OC NEI Bridge даёт компонент `nei` всем компьютерам.
Ему нужно хотя бы 1 МБ памяти. Hover Upgrade не нужен: `oc setup` поднимает `limitFlightHeight` до 256.

## Шаг 1. Navigation Upgrade

Navigation Upgrade отдаёт координаты относительно центра карты, из которой его скрафтили. Карта из `oc give`
имеет центр (0, 0) и масштаб 1, поэтому координаты робота совпадают с F3 в пределах ±128 блоков от (0, 0),
включая площадку демо. Новая карта или карта из творческой вкладки не подойдут: координаты будут смещены.

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
- **Memory (Tier 3.5)** ×2;
- **Hard Disk Drive (Tier 2)**;
- **EEPROM (Lua BIOS)**. Если в вкладке есть только пустой EEPROM, скрафтите его без формы вместе
  с OpenComputers Manual;
- **Internet Card**, **Graphics Card (Tier 1)**;
- **Inventory Controller Upgrade**, **Crafting Upgrade**, **Angel Upgrade**, **Inventory Upgrade** ×2;
- **Geolyzer**, **Screen (Tier 1)**, **Keyboard**, **Disk Drive**;
- дискета **OpenOS**. Если её нет во вкладке, скрафтите без формы Floppy Disk и OpenComputers Manual.

И ваш Navigation Upgrade из шага 1.

## Шаг 3. Сборка

Поставьте Electronics Assembler вне площадки демо (площадка это x 85..120, z 85..120), например у (80, 64, 100).
Питание не нужно: `oc setup` включает `ignorePower=true`.

ПКМ по сборщику, затем положите Computer Case (Tier 3) в его главный слот. Появятся слоты корпуса. Когда
вы наводите курсор на слот, предметы, которые в него подходят, подсвечиваются в инвентаре. В слот с
римской цифрой N влезает деталь уровня N и ниже.

| Слоты корпуса Tier 3 | Что положить | Сложность |
|---|---|---|
| Карты: T3, T2, T2 | Internet Card, Graphics Card (Tier 1) | 2 + 1 |
| CPU: T3 | CPU (Tier 3) | 0 |
| Память: T3, T3 | Memory (Tier 3.5) ×2, всего 2 МБ | 3 + 3 |
| EEPROM | EEPROM (Lua BIOS) | 0 |
| Диски: T3, T2 | Hard Disk Drive (Tier 2) | 2 |
| Апгрейды: T3 ×3 | Inventory Controller, Crafting, Navigation | 2 + 2 + 2 |
| Апгрейды: T2 ×3 | Angel, Geolyzer, Inventory Upgrade | 2 + 1 + 1 |
| Апгрейды: T1 ×3 | Screen (Tier 1), Keyboard, Inventory Upgrade | 1 + 1 + 1 |
| Контейнеры: T3, T2, T2 | Disk Drive в любой из них, остальные по желанию (ниже) | 2 |

Сложность получается 26 из 32, сборщик показывает её строкой `Complexity: 26/32`. Предел для корпуса Tier 3
с CPU Tier 3 равен 32. В сложность не входят корпус, CPU и EEPROM. Деталь уровня N стоит N, контейнер уровня N
стоит 2N. Disk Drive в роботе считается контейнером уровня 1, поэтому стоит 2 и ставится в контейнерный слот,
а не в слот апгрейда. Сборщик не запустится, если сумма выше предела.

Два Inventory Upgrade дают 32 слота инвентаря (каждый по 16). Сетка крафта занимает слоты 1–3, 5–7 и 9–11.
Чтобы позже добавлять апгрейды без пересборки, положите в свободный контейнерный слот **Upgrade Container (Tier 2)**:
сложность станет 30. В собранном роботе в этот контейнер вставляется любой апгрейд уровня 2 и ниже.

Нажмите кнопку запуска и дождитесь конца сборки, затем заберите робота из выходного слота. Собранного робота
изменить нельзя, только разобрать в Disassembler (детали при этом могут сломаться). Поэтому проверьте
раскладку до запуска.

## Шаг 4. Поставить робота и установить OpenOS

1. Поставьте робота на площадку, например на (96, 64, 105), но **не** на клетку склада (95, 64, 105):
   `oc up --reset` ставит туда сундук. Остальной сброс площадки робота не трогает. Полный сброс мира из шаблона
   (`prepare --fresh` или неудачный сброс региона) удаляет и робота.
2. ПКМ по роботу. Положите дискету OpenOS в слот дисковода в окне робота и нажмите кнопку питания.
3. OpenOS загрузится с дискеты. Выполните `install`, выберите жёсткий диск и подтвердите. После `reboot` робот
   грузится с диска, дискету можно забрать.

## Шаг 5. Подключить робота к мосту

`uv run oc up` печатает эти же команды. В шелле робота:

```
wget -f http://127.0.0.1:8770/get.lua /home/get.lua
/home/get.lua
oc_mcp
```

Установщик скачивает клиент oc-mcp в `/home` и дописывает `oc_mcp` в `/home/.shrc`, поэтому после перезапуска
сервера достаточно нажать кнопку питания. Робот печатает `oc-mcp polling http://127.0.0.1:8765` и молча опрашивает
мост, пока не запущен агент. Остановить скрипт можно через Ctrl+Alt+C.

## Шаг 6. Проверить

- В `/home/oc_mcp.log` на роботе (`edit /home/oc_mcp.log`) у каждого tool должно стоять `tool <name>: enabled`.
  Если стоит `disabled (missing component: X)`, значит, деталь X забыта (таблица в начале).
- Запустите агента (`cd demo/workspace`, затем `claude`) и попросите `вызови get_status робота`. Позиция должна
  совпасть с F3, когда вы стоите на месте робота, а `facing` с направлением робота.

## Если не работает

| Симптом | Причина |
|---|---|
| Сборщик не запускается, сложность выше 32 | Лишние или слишком высокие по уровню детали. Проверьте таблицу шага 3 |
| Сборщик не принимает деталь в слот | Уровень детали выше уровня слота: апгрейды T2 только в слоты T2 и T3 |
| Сборка стоит на месте | Нет питания: `uv run oc status` должен показать `opencomputers config ok`. Иначе остановите сервер и выполните `oc setup` |
| Робот не загружается: `no bios found; install a configured EEPROM` | EEPROM пустой или его нет: нужен EEPROM (Lua BIOS) |
| Робот не загружается: `no bootable medium found` | OpenOS не установлена на диск, и дискеты в дисководе нет |
| `get_status` без координат | Нет Navigation Upgrade |
| Координаты не совпадают с F3 | Navigation Upgrade скрафчен не с картой из `oc give` |
| `poll failed` в `oc_mcp.log` | Нет Internet Card, мост не запущен или не настроен `filteringRules` (`oc status`) |
| `place_at` отвечает ошибкой у висящих блоков | Нет Angel Upgrade: стройте снизу вверх |
